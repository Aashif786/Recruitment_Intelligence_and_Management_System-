from fastapi.routing import APIRoute
from fastapi import HTTPException, Request as FastAPIRequest, Response
from fastapi.responses import JSONResponse
from typing import Callable, Any
import json
import logging

logger = logging.getLogger(__name__)

def _decode_json_response_body(response: JSONResponse):
    body = getattr(response, "body", None)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None

def _headers_without_content_length(response: Response):
    out = {}
    for k, v in response.headers.items():
        lk = k.lower()
        if lk in ("content-length", "content-type"):
            continue
        out[k] = v
    return out

class StandardizedAPIRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()
        async def standardized_handler(request: FastAPIRequest) -> Any:
            try:
                response = await original_handler(request)
                if isinstance(response, JSONResponse):
                    payload = _decode_json_response_body(response)
                    if isinstance(payload, dict) and "success" in payload:
                        return response
                    
                    error_msg = None
                    if response.status_code >= 400:
                         if isinstance(payload, dict):
                              error_msg = payload.get("error") or payload.get("detail") or "Error"
                         else:
                              error_msg = str(payload) or "Error"

                    return JSONResponse(
                        status_code=response.status_code,
                        content={
                            "success": response.status_code < 400,
                            "data": payload,
                            "error": error_msg
                        },
                        headers=_headers_without_content_length(response),
                    )
                if hasattr(response, "status_code"):
                    return response
                return {
                    "success": True,
                    "data": response,
                    "error": None
                }
            except HTTPException as exc:
                raise exc
            except Exception as exc:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"[GLOBAL ERROR] Handler crash in {request.url.path}: {str(exc)}\n{error_trace}")
                raise exc
        return standardized_handler
