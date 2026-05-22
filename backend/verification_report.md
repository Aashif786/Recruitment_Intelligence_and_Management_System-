# RIMS Production Readiness Verification Report

Generated at: `2026-05-22T11:24:50.065873+00:00`

> [!NOTE]
> **SUCCESS**: All verification tests passed. RIMS backend is production-ready!

## Execution Summary Table

| Verification Tier | Status | Duration | Exit Code |
| :--- | :---: | :---: | :---: |
| Tier 1: Core Pytest Suite | ✅ PASSED | `73.09s` | `0` |
| Tier 2: AI Client Resilience & Resolution | ✅ PASSED | `2.59s` | `0` |
| Tier 2: Enterprise Schema & Signature Validators | ✅ PASSED | `0.67s` | `0` |
| Tier 2: Idempotency & Ephemeral Replay Cache | ✅ PASSED | `1.60s` | `0` |
| Tier 2: WebSocket Submit Idempotency | ✅ PASSED | `6.65s` | `0` |
| Tier 3: Production Smoke Verification | ✅ PASSED | `5.87s` | `0` |
| **Total** | | **`90.46s`** | |

## Detailed Execution Logs

### Tier 1: Core Pytest Suite

- **Exit Code**: `0`
- **Duration**: `73.09s`

**Standard Output**:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-8.3.4, pluggy-1.6.0 -- C:\Users\user\Desktop\PROJECT\rims\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\user\Desktop\PROJECT\rims\backend
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.12.1
collecting ... collected 311 items

tests/onboarding_isolation/test_01_unit.py::test_unit_employee_id_format PASSED [  0%]
tests/onboarding_isolation/test_01_unit.py::test_unit_candidate_states PASSED [  0%]
tests/onboarding_isolation/test_02_integration.py::test_integration_job_ownership_propagation PASSED [  0%]
tests/onboarding_isolation/test_02_integration.py::test_integration_settings_template_check PASSED [  1%]
tests/onboarding_isolation/test_02_integration.py::test_integration_notification_trigger PASSED [  1%]
tests/onboarding_isolation/test_03_api.py::test_api_candidates_list_schema PASSED [  1%]
tests/onboarding_isolation/test_03_api.py::test_api_invalid_application_id PASSED [  2%]
tests/onboarding_isolation/test_03_api.py::test_api_analytics_schema PASSED [  2%]
tests/onboarding_isolation/test_04_functional.py::test_functional_full_lifecycle PASSED [  2%]
tests/onboarding_isolation/test_04_functional.py::test_functional_link_expiry_check PASSED [  3%]
tests/onboarding_isolation/test_05_e2e.py::test_e2e_full_onboarding_journey PASSED [  3%]
tests/onboarding_isolation/test_06_database.py::test_database_persistence PASSED [  3%]
tests/onboarding_isolation/test_07_ui_ux.py::test_ui_ux_responsive_audit PASSED [  4%]
tests/onboarding_isolation/test_08_regression.py::test_regression_candidate_filtering PASSED [  4%]
tests/onboarding_isolation/test_09_system.py::test_system_audit_trail PASSED [  4%]
tests/onboarding_isolation/test_10_security.py::test_security_hr_isolation PASSED [  5%]
tests/onboarding_isolation/test_10_security.py::test_security_candidate_role_restriction PASSED [  5%]
tests/onboarding_isolation/test_10_security.py::test_security_unauthenticated_access PASSED [  5%]
tests/onboarding_isolation/test_10_security.py::test_security_token_tampering PASSED [  6%]
tests/onboarding_isolation/test_11_performance.py::test_performance_candidates_listing_latency PASSED [  6%]
tests/onboarding_isolation/test_11_performance.py::test_performance_analytics_query_speed PASSED [  6%]
tests/onboarding_isolation/test_12_compatibility.py::test_compatibility_date_formats PASSED [  7%]
tests/onboarding_isolation/test_13_smoke.py::test_smoke_onboarding_health PASSED [  7%]
tests/onboarding_isolation/test_14_sanity.py::test_sanity_past_date_blocking PASSED [  7%]
tests/onboarding_isolation/test_14_sanity.py::test_sanity_future_date_allowance PASSED [  8%]
tests/onboarding_isolation/test_15_uat.py::test_uat_onboarding_window_rule PASSED [  8%]
tests/test_api_endpoints.py::TestAuthEndpoints::test_register_valid_candidate PASSED [  8%]
tests/test_api_endpoints.py::TestAuthEndpoints::test_register_duplicate_email_rejected PASSED [  9%]
tests/test_api_endpoints.py::TestAuthEndpoints::test_register_invalid_email_rejected PASSED [  9%]
tests/test_api_endpoints.py::TestAuthEndpoints::test_login_with_nonexistent_email_returns_401 PASSED [  9%]
tests/test_api_endpoints.py::TestAuthEndpoints::test_login_invalid_email_format_returns_422 PASSED [  9%]
tests/test_api_endpoints.py::TestAuthEndpoints::test_forgot_password_unknown_email_returns_200 PASSED [ 10%]
tests/test_api_endpoints.py::TestAuthEndpoints::test_forgot_password_invalid_email_returns_422 PASSED [ 10%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_get_public_jobs_no_auth PASSED [ 10%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_get_all_jobs_requires_auth PASSED [ 11%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_get_all_jobs_authenticated_hr PASSED [ 11%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_create_job_requires_hr_auth PASSED [ 11%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_create_job_with_valid_data PASSED [ 12%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_create_job_numeric_title_rejected PASSED [ 12%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_create_job_short_description_rejected PASSED [ 12%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_create_job_invalid_duration_rejected PASSED [ 13%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_update_job_requires_hr_auth PASSED [ 13%]
tests/test_api_endpoints.py::TestJobsEndpoints::test_update_job_as_hr PASSED [ 13%]
tests/test_api_endpoints.py::TestApplicationsEndpoints::test_get_all_applications_requires_auth PASSED [ 14%]
tests/test_api_endpoints.py::TestApplicationsEndpoints::test_get_all_applications_as_hr PASSED [ 14%]
tests/test_api_endpoints.py::TestApplicationsEndpoints::test_apply_invalid_name_rejected PASSED [ 14%]
tests/test_api_endpoints.py::TestApplicationsEndpoints::test_apply_invalid_email_rejected PASSED [ 15%]
tests/test_api_endpoints.py::TestApplicationsEndpoints::test_apply_short_phone_rejected PASSED [ 15%]
tests/test_api_endpoints.py::TestApplicationsEndpoints::test_get_application_detail_as_hr PASSED [ 15%]
tests/test_api_endpoints.py::TestApplicationsEndpoints::test_get_application_detail_no_auth PASSED [ 16%]
tests/test_api_endpoints.py::TestApplicationsEndpoints::test_candidate_cannot_edit_job PASSED [ 16%]
tests/test_api_endpoints.py::TestNotificationsEndpoints::test_get_notifications_requires_auth PASSED [ 16%]
tests/test_api_endpoints.py::TestNotificationsEndpoints::test_get_notifications_as_hr PASSED [ 17%]
tests/test_api_endpoints.py::TestNotificationsEndpoints::test_get_notifications_as_candidate PASSED [ 17%]
tests/test_api_endpoints.py::TestSettingsEndpoints::test_get_settings_public PASSED [ 17%]
tests/test_api_endpoints.py::TestSettingsEndpoints::test_get_settings_as_hr PASSED [ 18%]
tests/test_api_endpoints.py::TestAnalyticsEndpoints::test_analytics_requires_auth PASSED [ 18%]
tests/test_api_endpoints.py::TestAnalyticsEndpoints::test_analytics_as_hr PASSED [ 18%]
tests/test_api_endpoints.py::TestTicketsEndpoints::test_get_tickets_requires_auth PASSED [ 18%]
tests/test_api_endpoints.py::TestTicketsEndpoints::test_get_tickets_as_hr PASSED [ 19%]
tests/test_api_endpoints.py::TestTicketsEndpoints::test_get_ticket_detail_not_found PASSED [ 19%]
tests/test_api_endpoints.py::TestHealthEndpoints::test_root_endpoint_accessible PASSED [ 19%]
tests/test_api_endpoints.py::TestHealthEndpoints::test_docs_endpoint_accessible PASSED [ 20%]
tests/test_api_endpoints.py::TestCORSBehavior::test_cors_header_present_for_allowed_origin PASSED [ 20%]
tests/test_api_endpoints.py::TestPaginationParameters::test_jobs_pagination_params_accepted PASSED [ 20%]
tests/test_api_endpoints.py::TestPaginationParameters::test_applications_pagination_params_accepted PASSED [ 21%]
tests/test_audit_validation.py::test_job_creation_rejects_numeric_title PASSED [ 21%]
tests/test_audit_validation.py::test_job_creation_rejects_short_description PASSED [ 21%]
tests/test_audit_validation.py::test_application_validation_direct PASSED [ 22%]
tests/test_audit_validation.py::test_cors_aware_rate_limit_fallback PASSED [ 22%]
tests/test_auth.py::test_register_candidate PASSED                       [ 22%]
tests/test_auth.py::test_login_invalid_credentials PASSED                [ 23%]
tests/test_auth.py::test_idor_job_access PASSED                          [ 23%]
tests/test_core_utilities.py::TestEmailValidation::test_valid_email_returns_normalized PASSED [ 23%]
tests/test_core_utilities.py::TestEmailValidation::test_numeric_local_part_raises PASSED [ 24%]
tests/test_core_utilities.py::TestEmailValidation::test_disposable_domain_rejected PASSED [ 24%]
tests/test_core_utilities.py::TestEmailValidation::test_missing_at_symbol_raises PASSED [ 24%]
tests/test_core_utilities.py::TestEmailValidation::test_empty_email_raises PASSED [ 25%]
tests/test_core_utilities.py::TestEmailValidation::test_valid_subdomain_email PASSED [ 25%]
tests/test_core_utilities.py::TestEmailValidation::test_all_disposable_domains_blocked PASSED [ 25%]
tests/test_core_utilities.py::TestEmailValidation::test_guerrillamail_rejected PASSED [ 26%]
tests/test_core_utilities.py::TestEmailValidation::test_enterprise_valid_email PASSED [ 26%]
tests/test_core_utilities.py::TestEmailValidation::test_enterprise_no_ip_still_works PASSED [ 26%]
tests/test_core_utilities.py::TestPhoneUtils::test_none_input_returns_none_none PASSED [ 27%]
tests/test_core_utilities.py::TestPhoneUtils::test_empty_string_returns_empty_none PASSED [ 27%]
tests/test_core_utilities.py::TestPhoneUtils::test_plain_10_digit_number PASSED [ 27%]
tests/test_core_utilities.py::TestPhoneUtils::test_international_format_normalized PASSED [ 27%]
tests/test_core_utilities.py::TestPhoneUtils::test_letters_rejected PASSED [ 28%]
tests/test_core_utilities.py::TestPhoneUtils::test_invalid_chars_rejected PASSED [ 28%]
tests/test_core_utilities.py::TestPhoneUtils::test_too_short_rejected PASSED [ 28%]
tests/test_core_utilities.py::TestPhoneUtils::test_too_long_rejected PASSED [ 29%]
tests/test_core_utilities.py::TestPhoneUtils::test_india_prefix_stripped PASSED [ 29%]
tests/test_core_utilities.py::TestPhoneUtils::test_leading_zeros_stripped PASSED [ 29%]
tests/test_core_utilities.py::TestPhoneUtils::test_formatted_us_number PASSED [ 30%]
tests/test_core_utilities.py::TestPhoneUtils::test_hash_is_deterministic PASSED [ 30%]
tests/test_core_utilities.py::TestPhoneUtils::test_hash_length_is_64 PASSED [ 30%]
tests/test_core_utilities.py::TestPhoneUtils::test_different_numbers_different_hashes PASSED [ 31%]
tests/test_core_utilities.py::TestPhoneUtils::test_none_input_returns_none PASSED [ 31%]
tests/test_core_utilities.py::TestPhoneUtils::test_empty_string_returns_none PASSED [ 31%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_lowercase_pdf_extension PASSED [ 32%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_lowercase_docx_extension PASSED [ 32%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_mixed_case_doc_extension PASSED [ 32%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_no_extension_returns_empty PASSED [ 33%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_none_filename_returns_empty PASSED [ 33%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_valid_pdf_signature PASSED [ 33%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_valid_docx_signature PASSED [ 34%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_valid_doc_signature PASSED [ 34%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_pdf_signature_mismatch_rejected PASSED [ 34%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_docx_signature_mismatch_rejected PASSED [ 35%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_empty_content_rejected PASSED [ 35%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_unknown_extension_accepted PASSED [ 35%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_filename_ends_with_correct_extension PASSED [ 36%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_filename_no_path_traversal PASSED [ 36%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_same_inputs_same_filename PASSED [ 36%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_different_emails_different_filenames PASSED [ 36%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_different_content_different_filenames PASSED [ 37%]
tests/test_core_utilities.py::TestResumeUploadUtils::test_extension_without_leading_dot PASSED [ 37%]
tests/test_core_utilities.py::TestEncryptionUtils::test_none_is_not_encrypted PASSED [ 37%]
tests/test_core_utilities.py::TestEncryptionUtils::test_empty_string_is_not_encrypted PASSED [ 38%]
tests/test_core_utilities.py::TestEncryptionUtils::test_short_string_is_not_encrypted PASSED [ 38%]
tests/test_core_utilities.py::TestEncryptionUtils::test_plain_text_is_not_encrypted PASSED [ 38%]
tests/test_core_utilities.py::TestEncryptionUtils::test_encrypt_decrypt_round_trip PASSED [ 39%]
tests/test_core_utilities.py::TestEncryptionUtils::test_encrypt_none_returns_none PASSED [ 39%]
tests/test_core_utilities.py::TestEncryptionUtils::test_decrypt_none_returns_none PASSED [ 39%]
tests/test_core_utilities.py::TestEncryptionUtils::test_decrypt_plain_text_returns_as_is PASSED [ 40%]
tests/test_core_utilities.py::TestEncryptionUtils::test_encrypt_already_encrypted_is_idempotent PASSED [ 40%]
tests/test_core_utilities.py::TestEncryptionUtils::test_encrypted_value_starts_with_gAAAAA PASSED [ 40%]
tests/test_core_utilities.py::TestEncryptionUtils::test_encrypt_non_string_coerced PASSED [ 41%]
tests/test_core_utilities.py::TestEncryptionUtils::test_decrypt_invalid_fernet_token_returns_unreadable PASSED [ 41%]
tests/test_core_utilities.py::TestEncryptionUtils::test_empty_string_encrypted_and_decrypted PASSED [ 41%]
tests/test_core_utilities.py::TestConfigAllowedOrigins::test_single_origin_returned_as_list PASSED [ 42%]
tests/test_core_utilities.py::TestConfigAllowedOrigins::test_multiple_origins_parsed PASSED [ 42%]
tests/test_core_utilities.py::TestConfigAllowedOrigins::test_whitespace_stripped_from_origins PASSED [ 42%]
tests/test_core_utilities.py::TestConfigAllowedOrigins::test_empty_origins_string_returns_empty_list PASSED [ 43%]
tests/test_core_utilities.py::TestConfigAllowedOrigins::test_default_frontend_base_url PASSED [ 43%]
tests/test_core_utilities.py::TestConstantsIntegrity::test_all_candidate_states_are_strings PASSED [ 43%]
tests/test_core_utilities.py::TestConstantsIntegrity::test_all_transition_actions_are_strings PASSED [ 44%]
tests/test_core_utilities.py::TestConstantsIntegrity::test_no_duplicate_state_values PASSED [ 44%]
tests/test_core_utilities.py::TestConstantsIntegrity::test_no_duplicate_action_values PASSED [ 44%]
tests/test_core_utilities.py::TestConstantsIntegrity::test_key_states_exist PASSED [ 45%]
tests/test_hardened_system.py::test_secure_login_issues_httponly_cookie PASSED [ 45%]
tests/test_hardened_system.py::test_unauthorized_access_rejected PASSED  [ 45%]
tests/test_hardened_system.py::test_ai_sanitization_defense PASSED       [ 45%]
tests/test_hardened_system.py::test_async_job_queue_polling PASSED       [ 46%]
tests/test_hardened_system.py::test_concurrent_application_submissions PASSED [ 46%]
tests/test_hardened_system.py::test_malicious_file_upload_rejected PASSED [ 46%]
tests/test_hardened_system.py::test_brute_force_rate_limit_auth PASSED   [ 47%]
tests/test_hardened_system.py::test_prompt_injection_fallback_defense[asyncio] PASSED [ 47%]
tests/test_models_orm.py::TestUserModel::test_create_hr_user PASSED      [ 47%]
tests/test_models_orm.py::TestUserModel::test_create_candidate_user PASSED [ 48%]
tests/test_models_orm.py::TestUserModel::test_user_defaults PASSED       [ 48%]
tests/test_models_orm.py::TestUserModel::test_user_email_unique_constraint PASSED [ 48%]
tests/test_models_orm.py::TestUserModel::test_user_created_at_auto_populated PASSED [ 49%]
tests/test_models_orm.py::TestUserModel::test_fixture_hr_user_has_correct_role PASSED [ 49%]
tests/test_models_orm.py::TestUserModel::test_fixture_candidate_user_has_correct_role PASSED [ 49%]
tests/test_models_orm.py::TestJobModel::test_create_job PASSED           [ 50%]
tests/test_models_orm.py::TestJobModel::test_job_default_status_is_open PASSED [ 50%]
tests/test_models_orm.py::TestJobModel::test_job_default_duration_is_60 PASSED [ 50%]
tests/test_models_orm.py::TestJobModel::test_job_default_aptitude_disabled PASSED [ 51%]
tests/test_models_orm.py::TestJobModel::test_job_hr_relationship PASSED  [ 51%]
tests/test_models_orm.py::TestJobModel::test_job_with_aptitude_enabled PASSED [ 51%]
tests/test_models_orm.py::TestJobModel::test_query_job_by_id PASSED      [ 52%]
tests/test_models_orm.py::TestApplicationModel::test_create_application PASSED [ 52%]
tests/test_models_orm.py::TestApplicationModel::test_application_default_resume_status PASSED [ 52%]
tests/test_models_orm.py::TestApplicationModel::test_application_default_scores_zero PASSED [ 53%]
tests/test_models_orm.py::TestApplicationModel::test_sample_application_fixture PASSED [ 53%]
tests/test_models_orm.py::TestApplicationModel::test_application_unique_job_email_constraint PASSED [ 53%]
tests/test_models_orm.py::TestApplicationModel::test_application_notes_encrypted PASSED [ 54%]
tests/test_models_orm.py::TestApplicationModel::test_application_status_update PASSED [ 54%]
tests/test_models_orm.py::TestInterviewModel::test_create_interview PASSED [ 54%]
tests/test_models_orm.py::TestInterviewModel::test_interview_default_status PASSED [ 54%]
tests/test_models_orm.py::TestInterviewModel::test_interview_status_update PASSED [ 55%]
tests/test_models_orm.py::TestInterviewModel::test_interview_default_duration PASSED [ 55%]
tests/test_models_orm.py::TestInterviewModel::test_interview_application_relationship PASSED [ 55%]
tests/test_models_orm.py::TestInterviewQuestionsAnswers::test_create_question PASSED [ 56%]
tests/test_models_orm.py::TestInterviewQuestionsAnswers::test_create_answer_for_question PASSED [ 56%]
tests/test_models_orm.py::TestInterviewQuestionsAnswers::test_answer_text_encrypted_round_trip PASSED [ 56%]
tests/test_models_orm.py::TestAuditLogModel::test_create_audit_log PASSED [ 57%]
tests/test_models_orm.py::TestAuditLogModel::test_audit_log_no_user_id PASSED [ 57%]
tests/test_models_orm.py::TestNotificationModel::test_create_notification PASSED [ 57%]
tests/test_models_orm.py::TestNotificationModel::test_notification_message_encrypted PASSED [ 58%]
tests/test_models_orm.py::TestNotificationModel::test_mark_notification_read PASSED [ 58%]
tests/test_models_orm.py::TestHiringDecisionModel::test_create_hiring_decision PASSED [ 58%]
tests/test_models_orm.py::TestHiringDecisionModel::test_create_rejection_decision PASSED [ 59%]
tests/test_models_orm.py::TestGlobalSettingsModel::test_create_setting PASSED [ 59%]
tests/test_models_orm.py::TestGlobalSettingsModel::test_setting_unique_key_constraint PASSED [ 59%]
tests/test_onboarding_exhaustive.py::test_security_hr_isolation PASSED   [ 60%]
tests/test_onboarding_exhaustive.py::test_functional_staged_offer_workflow PASSED [ 60%]
tests/test_onboarding_exhaustive.py::test_database_id_generation_uniqueness PASSED [ 60%]
tests/test_onboarding_exhaustive.py::test_compatibility_date_parsing PASSED [ 61%]
tests/test_onboarding_exhaustive.py::test_performance_bulk_latency PASSED [ 61%]
tests/test_onboarding_exhaustive.py::test_system_audit_log_completeness PASSED [ 61%]
tests/test_onboarding_exhaustive.py::test_sanity_upcoming_count_logic PASSED [ 62%]
tests/test_onboarding_exhaustive.py::test_resend_offer_success_and_audit PASSED [ 62%]
tests/test_onboarding_full.py::test_onboarding_smoke_endpoints PASSED    [ 62%]
tests/test_onboarding_full.py::test_issue_offer_letter_past_date_blocked PASSED [ 63%]
tests/test_onboarding_full.py::test_issue_offer_letter_success_transition PASSED [ 63%]
tests/test_onboarding_full.py::test_onboarding_completion_flow PASSED    [ 63%]
tests/test_onboarding_full.py::test_onboarding_analytics_speed PASSED    [ 63%]
tests/test_onboarding_full.py::test_id_card_generation_guard PASSED      [ 64%]
tests/test_password_security.py::test_password_validation_valid PASSED   [ 64%]
tests/test_password_security.py::test_password_validation_too_short PASSED [ 64%]
tests/test_password_security.py::test_password_validation_missing_upper PASSED [ 65%]
tests/test_password_security.py::test_password_validation_missing_lower PASSED [ 65%]
tests/test_password_security.py::test_password_validation_missing_digit PASSED [ 65%]
tests/test_password_security.py::test_password_validation_missing_special PASSED [ 66%]
tests/test_password_security.py::test_reset_password_validation PASSED   [ 66%]
tests/test_schemas_validation.py::TestUserRegisterSchema::test_valid_registration PASSED [ 66%]
tests/test_schemas_validation.py::TestUserRegisterSchema::test_email_is_lowercased_and_trimmed PASSED [ 67%]
tests/test_schemas_validation.py::TestUserRegisterSchema::test_missing_at_symbol_raises PASSED [ 67%]
tests/test_schemas_validation.py::TestUserRegisterSchema::test_multiple_at_symbols_raises PASSED [ 67%]
tests/test_schemas_validation.py::TestUserRegisterSchema::test_double_dot_raises PASSED [ 68%]
tests/test_schemas_validation.py::TestUserRegisterSchema::test_domain_starting_dot_raises PASSED [ 68%]
tests/test_schemas_validation.py::TestUserRegisterSchema::test_email_ending_in_dot_raises PASSED [ 68%]
tests/test_schemas_validation.py::TestUserRegisterSchema::test_empty_email_raises PASSED [ 69%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_valid_job PASSED [ 69%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_title_stripped_of_whitespace PASSED [ 69%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_optional_fields_default_correctly PASSED [ 70%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_numeric_only_title_raises PASSED [ 70%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_too_short_title_raises PASSED [ 70%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_special_char_title_raises PASSED [ 71%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_allowed_symbols_in_title PASSED [ 71%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_dotnet_title_accepted PASSED [ 71%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_short_description_raises PASSED [ 72%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_numeric_only_description_raises PASSED [ 72%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_duration_too_low_raises PASSED [ 72%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_duration_too_high_raises PASSED [ 72%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_boundary_duration_accepted PASSED [ 73%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_valid_requirements_accepted PASSED [ 73%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_too_short_requirements_raises PASSED [ 73%]
tests/test_schemas_validation.py::TestJobCreateSchema::test_none_requirements_accepted PASSED [ 74%]
tests/test_schemas_validation.py::TestJobUpdateSchema::test_empty_update_is_valid PASSED [ 74%]
tests/test_schemas_validation.py::TestJobUpdateSchema::test_update_title_validates PASSED [ 74%]
tests/test_schemas_validation.py::TestJobUpdateSchema::test_update_duration_validates PASSED [ 75%]
tests/test_schemas_validation.py::TestJobUpdateSchema::test_valid_partial_update PASSED [ 75%]
tests/test_schemas_validation.py::TestApplicationResponseScoreClamping::test_normal_scores_pass_through PASSED [ 75%]
tests/test_schemas_validation.py::TestApplicationResponseScoreClamping::test_score_above_100_clamped PASSED [ 76%]
tests/test_schemas_validation.py::TestApplicationResponseScoreClamping::test_score_below_0_clamped PASSED [ 76%]
tests/test_schemas_validation.py::TestApplicationResponseScoreClamping::test_none_score_becomes_zero PASSED [ 76%]
tests/test_schemas_validation.py::TestApplicationResponseScoreClamping::test_string_score_coerced_to_float PASSED [ 77%]
tests/test_schemas_validation.py::TestApplicationResponseScoreClamping::test_invalid_string_score_becomes_zero PASSED [ 77%]
tests/test_schemas_validation.py::TestResumeExtractionResponseSchema::test_valid_extraction PASSED [ 77%]
tests/test_schemas_validation.py::TestResumeExtractionResponseSchema::test_reasoning_json_string_parsed PASSED [ 78%]
tests/test_schemas_validation.py::TestResumeExtractionResponseSchema::test_reasoning_invalid_json_returns_error_dict PASSED [ 78%]
tests/test_schemas_validation.py::TestResumeExtractionResponseSchema::test_reasoning_dict_passthrough PASSED [ 78%]
tests/test_schemas_validation.py::TestResumeExtractionResponseSchema::test_score_clamped_above_100 PASSED [ 79%]
tests/test_schemas_validation.py::TestInterviewReportResponseSchema::test_valid_report PASSED [ 79%]
tests/test_schemas_validation.py::TestInterviewReportResponseSchema::test_negative_score_clamped_to_zero PASSED [ 79%]
tests/test_schemas_validation.py::TestInterviewReportResponseSchema::test_score_above_100_clamped PASSED [ 80%]
tests/test_schemas_validation.py::TestInterviewReportResponseSchema::test_none_score_becomes_zero PASSED [ 80%]
tests/test_schemas_validation.py::TestInterviewReportResponseSchema::test_reasoning_parsed_from_json_string PASSED [ 80%]
tests/test_schemas_validation.py::TestInterviewReportResponseSchema::test_reasoning_invalid_json_has_error_key PASSED [ 81%]
tests/test_schemas_validation.py::TestTicketSchemas::test_valid_issue_create PASSED [ 81%]
tests/test_schemas_validation.py::TestTicketSchemas::test_valid_issue_resolve PASSED [ 81%]
tests/test_schemas_validation.py::TestTicketSchemas::test_resolve_without_hr_response_defaults_empty PASSED [ 81%]
tests/test_schemas_validation.py::TestTicketSchemas::test_send_email_defaults_true PASSED [ 82%]
tests/test_schemas_validation.py::TestAuthResponseSchemas::test_token_response_defaults_bearer PASSED [ 82%]
tests/test_schemas_validation.py::TestAuthResponseSchemas::test_user_response_from_orm_like_dict PASSED [ 82%]
tests/test_schemas_validation.py::TestAuthResponseSchemas::test_user_response_created_at_iso_string_parsed PASSED [ 83%]
tests/test_schemas_validation.py::TestPasswordSchemas::test_forgot_password_valid_email PASSED [ 83%]
tests/test_schemas_validation.py::TestPasswordSchemas::test_forgot_password_invalid_email_raises PASSED [ 83%]
tests/test_schemas_validation.py::TestPasswordSchemas::test_reset_password_valid PASSED [ 84%]
tests/test_schemas_validation.py::TestPasswordSchemas::test_reset_password_invalid_email_raises PASSED [ 84%]
tests/test_schemas_validation.py::TestInterviewFeedbackSchema::test_valid_feedback PASSED [ 84%]
tests/test_schemas_validation.py::TestInterviewFeedbackSchema::test_feedback_text_is_optional PASSED [ 85%]
tests/test_schemas_validation.py::TestApplicationListResponseSchema::test_empty_items PASSED [ 85%]
tests/test_state_machine.py::TestValidateTransition::test_applied_to_screened_via_system_parsing_complete PASSED [ 85%]
tests/test_state_machine.py::TestValidateTransition::test_applied_reject PASSED [ 86%]
tests/test_state_machine.py::TestValidateTransition::test_screened_reject PASSED [ 86%]
tests/test_state_machine.py::TestValidateTransition::test_interview_completed_to_hired PASSED [ 86%]
tests/test_state_machine.py::TestValidateTransition::test_interview_completed_to_review_later PASSED [ 87%]
tests/test_state_machine.py::TestValidateTransition::test_hired_to_offer_sent PASSED [ 87%]
tests/test_state_machine.py::TestValidateTransition::test_offer_sent_to_accepted PASSED [ 87%]
tests/test_state_machine.py::TestValidateTransition::test_accepted_to_onboarded PASSED [ 88%]
tests/test_state_machine.py::TestValidateTransition::test_aptitude_round_to_ai_interview PASSED [ 88%]
tests/test_state_machine.py::TestValidateTransition::test_physical_interview_to_hired PASSED [ 88%]
tests/test_state_machine.py::TestInvalidTransitions::test_invalid_transition_raises_error PASSED [ 89%]
tests/test_state_machine.py::TestInvalidTransitions::test_terminal_state_onboarded_blocks_all PASSED [ 89%]
tests/test_state_machine.py::TestInvalidTransitions::test_terminal_state_rejected_blocks_all PASSED [ 89%]
tests/test_state_machine.py::TestInvalidTransitions::test_unknown_state_raises_invalid_transition PASSED [ 90%]
tests/test_state_machine.py::TestInvalidTransitions::test_offer_sent_to_hired_is_invalid PASSED [ 90%]
tests/test_state_machine.py::TestInvalidTransitions::test_screened_to_onboarded_is_invalid PASSED [ 90%]
tests/test_state_machine.py::TestResolveApproveTarget::test_approve_without_aptitude_goes_to_ai_interview PASSED [ 90%]
tests/test_state_machine.py::TestResolveApproveTarget::test_approve_with_aptitude_goes_to_aptitude_round PASSED [ 91%]
tests/test_state_machine.py::TestResolveApproveTarget::test_approve_with_no_job_defaults_to_ai_interview PASSED [ 91%]
tests/test_state_machine.py::TestGetAllowedActions::test_applied_has_expected_actions PASSED [ 91%]
tests/test_state_machine.py::TestGetAllowedActions::test_interview_completed_has_hire_and_reject PASSED [ 92%]
tests/test_state_machine.py::TestGetAllowedActions::test_terminal_state_has_no_actions PASSED [ 92%]
tests/test_state_machine.py::TestGetAllowedActions::test_rejected_has_no_actions PASSED [ 92%]
tests/test_state_machine.py::TestGetAllowedActions::test_unknown_state_returns_empty PASSED [ 93%]
tests/test_state_machine.py::TestCheckPreconditions::test_approve_from_applied_requires_resume_parsed PASSED [ 93%]
tests/test_state_machine.py::TestCheckPreconditions::test_approve_from_applied_with_parsed_status_passes PASSED [ 93%]
tests/test_state_machine.py::TestCheckPreconditions::test_hire_without_completed_interview_raises PASSED [ 94%]
tests/test_state_machine.py::TestCheckPreconditions::test_hire_with_completed_interview_passes PASSED [ 94%]
tests/test_state_machine.py::TestCheckPreconditions::test_call_for_interview_without_notes_and_incomplete_interview_raises PASSED [ 94%]
tests/test_state_machine.py::TestCheckPreconditions::test_call_for_interview_with_notes_and_incomplete_interview_passes PASSED [ 95%]
tests/test_state_machine.py::TestTransitionResult::test_repr_contains_key_info PASSED [ 95%]
tests/test_state_machine.py::TestTransitionResult::test_slots_accessible PASSED [ 95%]
tests/test_state_machine.py::TestGetUIButtonsForState::test_applied_state_has_reject_button PASSED [ 96%]
tests/test_state_machine.py::TestGetUIButtonsForState::test_interview_completed_has_hire_button PASSED [ 96%]
tests/test_state_machine.py::TestGetUIButtonsForState::test_every_state_has_view_report_button PASSED [ 96%]
tests/test_state_machine.py::TestGetUIButtonsForState::test_hired_state_has_send_for_approval PASSED [ 97%]
tests/test_state_machine.py::TestGetUIButtonsForState::test_buttons_have_required_keys PASSED [ 97%]
tests/test_state_machine.py::TestConstants::test_candidate_state_values PASSED [ 97%]
tests/test_state_machine.py::TestConstants::test_transition_action_values PASSED [ 98%]
tests/test_state_machine.py::TestConstants::test_terminal_states_immutable PASSED [ 98%]
tests/test_tickets_exhaustive.py::test_unauthenticated_api_endpoints PASSED [ 98%]
tests/test_tickets_exhaustive.py::test_candidate_issue_reporting_and_sanitization PASSED [ 99%]
tests/test_tickets_exhaustive.py::test_grievance_email_enumeration_protection PASSED [ 99%]
tests/test_tickets_exhaustive.py::test_collaborative_hr_ticket_resolution_flow PASSED [ 99%]
tests/test_tickets_exhaustive.py::test_candidate_support_ticket_creation PASSED [100%]

======================= 311 passed in 65.88s (0:01:05) ========================

```

---

### Tier 2: AI Client Resilience & Resolution

- **Exit Code**: `0`
- **Duration**: `2.59s`

**Standard Error / Diagnostics**:
```text
....
----------------------------------------------------------------------
Ran 4 tests in 0.005s

OK

```

---

### Tier 2: Enterprise Schema & Signature Validators

- **Exit Code**: `0`
- **Duration**: `0.67s`

**Standard Error / Diagnostics**:
```text
{"ts": "2026-05-22T16:54:35.869930", "event": "email_validation_rejected", "endpoint": "apply_for_job", "status": 400, "extra": {"reason": "disposable", "domain": "mailinator.com", "email_hash": "76296f9b6812"}}
.{"ts": "2026-05-22T16:54:35.878910", "event": "email_validation_rejected", "endpoint": "apply_for_job", "status": 400, "extra": {"reason": "invalid_format", "email_hash": "eba038945cb8"}}
..{"ts": "2026-05-22T16:54:35.883546", "event": "email_validation_rejected", "endpoint": "apply_for_job", "status": 400, "extra": {"reason": "numeric_local_part", "email_hash": "eb934be363f7"}}
.........
----------------------------------------------------------------------
Ran 12 tests in 0.116s

OK

```

---

### Tier 2: Idempotency & Ephemeral Replay Cache

- **Exit Code**: `0`
- **Duration**: `1.60s`

**Standard Error / Diagnostics**:
```text
....Redis ping failed; discarding client and reconnecting: boom
.
----------------------------------------------------------------------
Ran 5 tests in 0.031s

OK

```

---

### Tier 2: WebSocket Submit Idempotency

- **Exit Code**: `0`
- **Duration**: `6.65s`

**Standard Output**:
```text
2026-05-22 16:54:43,232 - root - INFO - Logging initialized. File logs saved to C:\Users\user\Desktop\PROJECT\rims\backend\logs
2026-05-22 16:54:43,232 - app.core.config - INFO - Environment config
2026-05-22 16:54:43,272 - app.migrations - INFO - Ensured question_sets table exists
2026-05-22 16:54:43,275 - app.migrations - INFO - Applying migration: Adding column interview_questions.question_options (TEXT)...
2026-05-22 16:54:43,276 - app.migrations - INFO - Migration SUCCESS: Column interview_questions.question_options added.
2026-05-22 16:54:43,276 - app.migrations - INFO - Applying migration: Adding column interview_questions.correct_option (INTEGER)...
2026-05-22 16:54:43,278 - app.migrations - INFO - Migration SUCCESS: Column interview_questions.correct_option added.
2026-05-22 16:54:43,290 - app.migrations - INFO - Applying migration: Adding column applications.notification_sent (BOOLEAN DEFAULT FALSE)...
2026-05-22 16:54:43,291 - app.migrations - INFO - Migration SUCCESS: Column applications.notification_sent added.
2026-05-22 16:54:43,306 - app.migrations - INFO - Applying migration: Adding column interviews.completed_at (TIMESTAMP)...
2026-05-22 16:54:43,307 - app.migrations - INFO - Migration SUCCESS: Column interviews.completed_at added.
2026-05-22 16:54:43,307 - app.migrations - INFO - Applying migration: Adding column interviews.termination_reason (VARCHAR(100))...
2026-05-22 16:54:43,308 - app.migrations - INFO - Migration SUCCESS: Column interviews.termination_reason added.
2026-05-22 16:54:43,309 - app.migrations - INFO - Applying migration: Adding column interviews.report_generated (BOOLEAN DEFAULT FALSE)...
2026-05-22 16:54:43,310 - app.migrations - INFO - Migration SUCCESS: Column interviews.report_generated added.
2026-05-22 16:54:43,311 - app.migrations - INFO - Applying migration: Adding column interviews.candidate_id (INTEGER REFERENCES users(id))...
2026-05-22 16:54:43,312 - app.migrations - INFO - Migration SUCCESS: Column interviews.candidate_id added.
2026-05-22 16:54:43,314 - app.migrations - INFO - Backfilled applications.resume_status from resume_extractions
2026-05-22 16:54:43,315 - app.migrations - INFO - Ensured global_settings table exists
2026-05-22 16:54:43,315 - app.migrations - INFO - Ensured interview_feedbacks table exists
2026-05-22 16:54:43,315 - app.migrations - WARNING - Error updating role constraint: (sqlite3.OperationalError) near "CONSTRAINT": syntax error
[SQL: ALTER TABLE users DROP CONSTRAINT IF EXISTS check_users_role]
(Background on this error at: https://sqlalche.me/e/20/e3q8)
2026-05-22 16:54:43,316 - app.migrations - WARNING - No super_admin_email configured. Skipping database super_admin role promotion.
2026-05-22 16:54:43,316 - app.migrations - INFO - Migration completed: normalized roles and promoted super admin
2026-05-22 16:54:43,318 - app.migrations - INFO - Migration completed: populated Application.hr_id
2026-05-22 16:54:43,318 - app.migrations - INFO - Migration completed: ensured index uq_application_job_email
2026-05-22 16:54:43,318 - app.migrations - INFO - Migration completed: ensured index uq_answer_per_question
2026-05-22 16:54:43,319 - app.migrations - INFO - Migration completed: ensured index uq_interview_application_id
2026-05-22 16:54:43,321 - app.migrations - INFO - Database schema and Enum validation passed.

```

**Standard Error / Diagnostics**:
```text
..
----------------------------------------------------------------------
Ran 2 tests in 0.205s

OK

```

---

### Tier 3: Production Smoke Verification

- **Exit Code**: `0`
- **Duration**: `5.87s`

**Standard Output**:
```text
2026-05-22 16:54:44,459 [INFO] ==================================================
2026-05-22 16:54:44,459 [INFO] RIMS PRODUCTION READINESS SMOKE TEST
2026-05-22 16:54:44,459 [INFO] Started at: 2026-05-22T11:24:44.459830+00:00
2026-05-22 16:54:44,459 [INFO] ==================================================
2026-05-22 16:54:44,460 [INFO] --- Testing Database Connectivity ---
2026-05-22 16:54:45,981 [INFO] SUCCESS: Database ping in 0.639s
2026-05-22 16:54:46,290 [INFO] STATS: Users=21, Applications=228
2026-05-22 16:54:46,316 [INFO] --- Testing Supabase Storage ---
2026-05-22 16:54:48,170 [INFO] HTTP Request: GET https://itajqbrebdbrunfqpbmg.supabase.co/storage/v1/bucket/resumes "HTTP/2 200 OK"
2026-05-22 16:54:48,171 [INFO] SUCCESS: Bucket 'resumes' is accessible
2026-05-22 16:54:48,235 [INFO] HTTP Request: GET https://itajqbrebdbrunfqpbmg.supabase.co/storage/v1/bucket/offers "HTTP/2 200 OK"
2026-05-22 16:54:48,249 [INFO] SUCCESS: Bucket 'offers' is accessible
2026-05-22 16:54:48,249 [INFO] --- Testing AI Services reachability ---
2026-05-22 16:54:48,951 [INFO] CONFIG: API Keys Present: {'OpenAI': False, 'Groq': True, 'Anthropic': False, 'Gemini': False}
2026-05-22 16:54:49,809 [INFO] HTTP Request: GET https://api.groq.com/openai/v1/models "HTTP/1.1 200 OK"
2026-05-22 16:54:49,810 [INFO] SUCCESS: Groq API reachability confirmed
2026-05-22 16:54:49,810 [INFO] ==================================================
2026-05-22 16:54:49,811 [INFO] SUCCESS: ALL SYSTEMS GO! RIMS is production-ready.

```

---

## E2E Playwright Browser Testing Guide

To verify the frontend system and live interview integration interactively:
1. **Start backend server**:
   ```powershell
   cd backend
   .\start.ps1 start
   ```
2. **Start frontend server**:
   ```bash
   cd frontend
   npm run dev
   ```
3. **Execute Playwright Tests**:
   ```bash
   cd frontend
   npx playwright test
   ```
