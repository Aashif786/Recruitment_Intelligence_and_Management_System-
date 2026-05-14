import logging
from app.core.timezone import get_ist_now

from app.core.config import get_settings
from app.core.ephemeral_result_cache import cache_get, cache_set
from app.core.idempotency import is_duplicate_request
from app.core.observability import log_json
from app.services.ai_orchestrator import evaluate_answer, generate_questions

from .adaptive_engine import adjust_difficulty
from .session_manager import session_manager

logger = logging.getLogger(__name__)
settings = get_settings()

from app.infrastructure.database import SessionLocal
from app.domain.models import Interview, InterviewQuestion, InterviewAnswer
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
settings = get_settings()

async def process_interview_message(session_id: str, data: dict):
    """Core logic controller backed by SQLAlchemy state."""
    db = SessionLocal()
    try:
        # 1. Fetch persistent session state
        interview_id = int(session_id) if str(session_id).isdigit() else 0
        interview = db.query(Interview).filter(Interview.id == interview_id).with_for_update().first()
        
        if not interview:
            await session_manager.send_personal_message({"type": "error", "message": "Invalid session."}, session_id)
            return

        action = data.get("action")
        
        # 2. Resuming logic in ACTION=START
        if action == "start":
            if interview.status == "not_started":
                interview.status = "in_progress"
                interview.started_at = get_ist_now()
                db.commit()
                logger.info(f"Starting fresh adaptive interview for ID {interview_id}")
            else:
                logger.info(f"Resuming existing interview for ID {interview_id} (Question {interview.questions_asked})")

            # If we've already asked questions, fetch the most recent unanswered one
            current_q = db.query(InterviewQuestion).filter(
                InterviewQuestion.interview_id == interview_id
            ).order_by(InterviewQuestion.question_number.desc()).first()
            
            if current_q:
                # Check if it was answered
                ans = db.query(InterviewAnswer).filter(InterviewAnswer.question_id == current_q.id).first()
                if not ans:
                    # Send existing question
                    await session_manager.send_personal_message({
                        "type": "question",
                        "question": current_q.question_text,
                        "difficulty": interview.current_difficulty or "medium",
                        "question_number": current_q.question_number,
                        "total_questions": interview.total_questions or 30,
                        "options": json.loads(current_q.options) if current_q.options else None,
                        "resumed": True
                    }, session_id)
                    return

            await _generate_and_send_next_question(db, interview, session_id)
            
        elif action == "submit_answer":
            answer_text = data.get("answer", "")
            # Find current active question
            current_q = db.query(InterviewQuestion).filter(
                InterviewQuestion.interview_id == interview_id
            ).order_by(InterviewQuestion.question_number.desc()).first()

            if not current_q:
                await session_manager.send_personal_message({"type": "error", "message": "No active question."}, session_id)
                return

            # Idempotency / Already Answered check
            existing_ans = db.query(InterviewAnswer).filter(InterviewAnswer.question_id == current_q.id).first()
            if existing_ans:
                await session_manager.send_personal_message({"type": "system", "message": "Answer already received."}, session_id)
                return

            request_id = (data.get("request_id") or data.get("x_request_id") or "").strip()
            replay_key = f"idem:ws.interview.evaluation:{session_id}:{request_id}" if request_id else ""

            if request_id and settings.enable_request_id_idempotency:
                cached_eval = cache_get(replay_key)
                if cached_eval:
                    await session_manager.send_personal_message(cached_eval, session_id)
                    return

            # Immediate acknowledgment & status heartbeat
            await session_manager.send_personal_message({"type": "system", "message": "Analyzing your response..."}, session_id)

            # Evaluate answer using the rubric from the question (if available)
            rubric = current_q.expected_points if isinstance(current_q.expected_points, list) else []
            eval_result = await evaluate_answer(
                current_q.question_text,
                answer_text,
                rubric or ["Technical concept", "Practical application"]
            )

            # --- START ATOMIC UPDATE BLOCK ---
            try:
                # 1. Persist the answer
                ans = InterviewAnswer(
                    interview_id=interview_id,
                    question_id=current_q.id,
                    answer_text=answer_text,
                    answer_score=eval_result.get("technical_accuracy", 5.0),
                    technical_score=eval_result.get("technical_accuracy", 5.0),
                    completeness_score=eval_result.get("completeness", 5.0),
                    clarity_score=eval_result.get("clarity", 5.0),
                    depth_score=eval_result.get("depth", 5.0),
                    practicality_score=eval_result.get("practicality", 5.0),
                    answer_evaluation=json.dumps(eval_result)
                )
                db.add(ans)

                # 2. Update difficulty and ask count
                new_difficulty = adjust_difficulty(interview.current_difficulty or "medium", eval_result.get("technical_accuracy", 5.0))
                interview.current_difficulty = new_difficulty
                interview.questions_asked += 1
                
                # Flush to ensure ID's are available but don't commit until we're done or next question is ready
                db.flush()

                eval_msg = {
                    "type": "evaluation",
                    "score": eval_result.get("technical_accuracy"),
                    "feedback": eval_result.get("feedback_text"),
                }
                if request_id: cache_set(replay_key, eval_msg)
                await session_manager.send_personal_message(eval_msg, session_id)
                
                # 3. Ending condition or generate next
                if interview.questions_asked >= (interview.total_questions or 10):
                    interview.status = "completed"
                    interview.ended_at = get_ist_now()
                    db.commit()
                    
                    await session_manager.send_personal_message({"type": "system", "message": "Evaluation complete. Finalizing results..."}, session_id)
                    # Critical: Trigger final report generation for WebSocket interviews
                    try:
                        from app.api.interviews import _finalize_interview_and_report_internal
                        await _finalize_interview_and_report_internal(db, interview_id)
                    except Exception as final_err:
                        logger.error(f"Failed to auto-generate report on finish: {final_err}")
                    
                    await session_manager.send_personal_message({"type": "end", "message": "Interview Complete. Grading..."}, session_id)
                else:
                    # Send informative heartbeat before question generation
                    await session_manager.send_personal_message({"type": "system", "message": "Adapting next question..."}, session_id)
                    await _generate_and_send_next_question(db, interview, session_id)
                    db.commit() # FINAL COMMIT for both evaluation and next question
            except Exception as atomic_err:
                db.rollback()
                logger.error(f"Atomic update failed: {atomic_err}", exc_info=True)
                raise atomic_err

        elif action == "jump_to_question":
            num = data.get("number")
            if not num: return
            
            logger.info(f"User jumping to question {num} for interview {interview_id}")
            
            # Fetch specific question
            q = db.query(InterviewQuestion).filter(
                InterviewQuestion.interview_id == interview_id,
                InterviewQuestion.question_number == num
            ).first()
            
            if q:
                # Check for answer
                ans = db.query(InterviewAnswer).filter(InterviewAnswer.question_id == q.id).first()
                await session_manager.send_personal_message({
                    "type": "question",
                    "question": q.question_text,
                    "difficulty": interview.current_difficulty or "medium",
                    "question_number": q.question_number,
                    "total_questions": interview.total_questions or 30,
                    "options": json.loads(q.options) if q.options else None,
                    "answer_text": ans.answer_text if ans else None,
                    "score": ans.answer_score if ans else None
                }, session_id)
            else:
                # If jumping to the NEXT immediate question that should be generated
                if num == interview.questions_asked + 1:
                    await session_manager.send_personal_message({"type": "system", "message": "Generating next challenge..."}, session_id)
                    await _generate_and_send_next_question(db, interview, session_id)
                    db.commit()
                else:
                    await session_manager.send_personal_message({"type": "error", "message": "Complete the current question first to move forward."}, session_id)

        elif action == "jump_to_section":
            section = data.get("section", "technical")
            # Set questions_asked to start of section if needed, or just let it flow
            target_q = 1
            if section == "technical": target_q = 11
            elif section == "behavioral": target_q = 26
            
            logger.info(f"User jumping to section: {section} (Q{target_q})")
            # Logic: If question exists, jump. If not, generate.
            q = db.query(InterviewQuestion).filter(
                InterviewQuestion.interview_id == interview_id,
                InterviewQuestion.question_number == target_q
            ).first()
            
            if q:
                await session_manager.send_personal_message({"type": "system", "message": f"Switching to {section.capitalize()}..."}, session_id)
                # reuse jump_to_question logic via recursion or just copy
                ans = db.query(InterviewAnswer).filter(InterviewAnswer.question_id == q.id).first()
                await session_manager.send_personal_message({
                    "type": "question",
                    "question": q.question_text,
                    "difficulty": interview.current_difficulty or "medium",
                    "question_number": q.question_number,
                    "total_questions": interview.total_questions or 30,
                    "options": json.loads(q.options) if q.options else None,
                    "answer_text": ans.answer_text if ans else None,
                    "score": ans.answer_score if ans else None
                }, session_id)
            else:
                # If target is next, generate
                if target_q == interview.questions_asked + 1:
                    await _generate_and_send_next_question(db, interview, session_id)
                    db.commit()
                else:
                    await session_manager.send_personal_message({"type": "error", "message": "Complete previous sections first."}, session_id)

    except Exception as e:
        logger.error(f"WS Controller Error: {e}", exc_info=True)
        db.rollback()
        await session_manager.send_personal_message({"type": "error", "message": "Internal processing error."}, session_id)
    finally:
        db.close()

async def _generate_and_send_next_question(db, interview, session_id: str):
    """Generate next question based on current difficulty and history."""
    # Fetch history for context
    history_ans = db.query(InterviewAnswer).filter(InterviewAnswer.interview_id == interview.id).all()
    history_context = [{"question": "Previously asked", "answer": a.answer_text} for a in history_ans] # Minimal summary

    # Determine round type based on question number
    q_num = interview.questions_asked + 1
    round_type = "Aptitude" if q_num <= 10 else "Technical" if q_num <= 25 else "Behavioral"
    
    # Simplified skill context for generator
    skills = ["Software Engineering"]
    if interview.application and interview.application.job:
        skills = [interview.application.job.title]

    question_data_list = await generate_questions(
        skills[0], 
        round_type, # Pass round_type as experience level/stage context
        skills, 
        history_context, 
        interview.current_difficulty or "medium"
    )
    
    # Extract question and rubric
    question_text = "Describe your experience with production systems."
    expected_points = ["Technical depth", "Problem solving"]
    
    if isinstance(question_data_list, dict):
        question_text = question_data_list.get("question", question_text)
        expected_points = question_data_list.get("expected_points", expected_points)
    elif isinstance(question_data_list, list) and len(question_data_list) > 0:
        # Fallback for older list-based legacy response
        question_text = question_data_list[0]

    # Persist the question with its rubric/options
    new_q = InterviewQuestion(
        interview_id=interview.id,
        question_number=q_num,
        question_text=question_text,
        question_type=round_type.lower(),
        expected_points=expected_points,
        options=json.dumps(expected_points) if round_type == "Aptitude" else None
    )
    db.add(new_q)
    db.commit()

    await session_manager.send_personal_message({
        "type": "question",
        "question": question_text,
        "difficulty": interview.current_difficulty or "medium",
        "question_number": q_num,
        "total_questions": interview.total_questions or 30,
        "options": expected_points if round_type == "Aptitude" else None
    }, session_id)