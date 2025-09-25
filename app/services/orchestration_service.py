"""
Intelligent Orchestration Service

This service manages the unified conversation flow for both web and WhatsApp platforms.
It handles step progression, phone collection, and lawyer notifications.
"""

import logging
import re
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from app.services.firebase_service import (
    get_conversation_flow,
    save_user_session,
    get_user_session,
    save_lead_data,
    get_firebase_service_status
)
from app.services.ai_chain import ai_orchestrator
from app.services.baileys_service import baileys_service
from app.services.lawyer_notification_service import lawyer_notification_service

logger = logging.getLogger(__name__)


class IntelligentHybridOrchestrator:
    """
    Unified orchestration service for web and WhatsApp conversations.
    Handles structured flow progression and AI fallback.
    """

    def __init__(self):
        self.gemini_unavailable_until = None
        self.gemini_check_interval = timedelta(minutes=5)

    async def process_message(
        self,
        message: str,
        session_id: str,
        phone_number: str = None,
        platform: str = "web"
    ) -> Dict[str, Any]:
        """
        Main entry point for processing messages from both web and WhatsApp.
        """
        try:
            logger.info(f"🎯 Processing message | platform={platform} | session={session_id} | msg='{message[:50]}...'")

            # Get or create session
            session_data = await self._get_or_create_session(session_id, platform, phone_number)
            
            # Check if collecting phone number
            if session_data.get("collecting_phone"):
                return await self._handle_phone_collection(message, session_id, session_data)
            
            # Check if flow is completed and should use AI
            if session_data.get("flow_completed") and session_data.get("phone_collected"):
                return await self._handle_ai_conversation(message, session_id, session_data)
            
            # Handle structured flow progression
            return await self._handle_structured_flow(message, session_id, session_data, platform)

        except Exception as e:
            logger.error(f"❌ Error in orchestration: {str(e)}")
            return {
                "response": "Desculpe, ocorreu um erro. Como posso ajudá-lo?",
                "response_type": "error_fallback",
                "session_id": session_id,
                "error": str(e)
            }

    async def _get_or_create_session(
        self,
        session_id: str,
        platform: str,
        phone_number: str = None
    ) -> Dict[str, Any]:
        """Get existing session or create new one."""
        session_data = await get_user_session(session_id)
        
        if not session_data:
            # Create new session
            session_data = {
                "session_id": session_id,
                "platform": platform,
                "current_step": 1,  # Start at step 1, not 0
                "flow_completed": False,
                "collecting_phone": False,
                "phone_collected": False,
                "ai_mode": False,
                "lead_data": {},
                "message_count": 0,
                "created_at": datetime.now(),
                "last_updated": datetime.now()
            }
            
            if phone_number:
                session_data["phone_number"] = phone_number
            
            await save_user_session(session_id, session_data)
            logger.info(f"✅ New session created | session={session_id} | platform={platform}")
        
        # Update message count
        session_data["message_count"] = session_data.get("message_count", 0) + 1
        session_data["last_updated"] = datetime.now()
        
        return session_data

    async def _handle_structured_flow(
        self,
        message: str,
        session_id: str,
        session_data: Dict[str, Any],
        platform: str
    ) -> Dict[str, Any]:
        """Handle the structured conversation flow."""
        try:
            # Get conversation flow from Firebase
            flow = await get_conversation_flow()
            current_step = session_data.get("current_step", 1)
            
            logger.info(f"📋 Handling structured flow | step={current_step} | platform={platform}")
            
            # Find current step in flow
            current_step_data = None
            for step in flow.get("steps", []):
                if step.get("id") == current_step:
                    current_step_data = step
                    break
            
            if not current_step_data:
                logger.error(f"❌ Step {current_step} not found in flow")
                return await self._complete_flow_and_collect_phone(session_id, session_data, flow)
            
            # If this is the first message (step 1) or start_conversation, return the question
            if current_step == 1 and (message.lower() in ["olá", "oi", "hello", "hi", "start_conversation"] or message == "start_conversation"):
                return {
                    "response": current_step_data["question"],
                    "response_type": "structured_question",
                    "session_id": session_id,
                    "current_step": current_step,
                    "flow_completed": False,
                    "ai_mode": False
                }
            
            # Validate and store the answer
            if not self._validate_answer(message, current_step):
                return {
                    "response": f"Por favor, forneça uma resposta mais completa. {current_step_data['question']}",
                    "response_type": "validation_error",
                    "session_id": session_id,
                    "current_step": current_step,
                    "flow_completed": False,
                    "ai_mode": False
                }
            
            # Store the answer
            field_name = f"step_{current_step}"
            session_data["lead_data"][field_name] = message.strip()
            
            # Move to next step
            next_step = current_step + 1
            next_step_data = None
            for step in flow.get("steps", []):
                if step.get("id") == next_step:
                    next_step_data = step
                    break
            
            if next_step_data:
                # Continue to next step
                session_data["current_step"] = next_step
                await save_user_session(session_id, session_data)
                
                return {
                    "response": next_step_data["question"],
                    "response_type": "structured_question",
                    "session_id": session_id,
                    "current_step": next_step,
                    "flow_completed": False,
                    "ai_mode": False
                }
            else:
                # Flow completed, move to phone collection
                return await self._complete_flow_and_collect_phone(session_id, session_data, flow)
                
        except Exception as e:
            logger.error(f"❌ Error in structured flow: {str(e)}")
            return {
                "response": "Desculpe, ocorreu um erro. Como posso ajudá-lo?",
                "response_type": "error_fallback",
                "session_id": session_id
            }

    async def _complete_flow_and_collect_phone(
        self,
        session_id: str,
        session_data: Dict[str, Any],
        flow: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Complete the structured flow and start phone collection."""
        try:
            # Mark flow as completed
            session_data["flow_completed"] = True
            session_data["collecting_phone"] = True
            
            # Save lead data
            lead_data = {
                "name": session_data["lead_data"].get("step_1", "Não informado"),
                "area_of_law": session_data["lead_data"].get("step_2", "Não informado"),
                "situation": session_data["lead_data"].get("step_3", "Não informado"),
                "wants_meeting": session_data["lead_data"].get("step_4", "Não informado"),
                "session_id": session_id,
                "platform": session_data.get("platform", "web"),
                "completed_at": datetime.now(),
                "status": "intake_completed"
            }
            
            lead_id = await save_lead_data(lead_data)
            session_data["lead_id"] = lead_id
            
            await save_user_session(session_id, session_data)
            
            phone_message = "Perfeito! Suas informações foram registradas. Agora, para finalizar, me informe seu número de WhatsApp com DDD (ex: 11999999999):"
            
            logger.info(f"✅ Flow completed, collecting phone | session={session_id} | lead_id={lead_id}")
            
            return {
                "response": phone_message,
                "response_type": "phone_collection",
                "session_id": session_id,
                "flow_completed": True,
                "collecting_phone": True,
                "lead_id": lead_id,
                "ai_mode": False
            }
            
        except Exception as e:
            logger.error(f"❌ Error completing flow: {str(e)}")
            return {
                "response": "Obrigado pelas informações! Como posso continuar ajudando?",
                "response_type": "completion_error",
                "session_id": session_id,
                "flow_completed": True,
                "ai_mode": True
            }

    async def _handle_phone_collection(
        self,
        message: str,
        session_id: str,
        session_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle phone number collection and validation."""
        try:
            phone_clean = re.sub(r'[^\d]', '', message)
            
            # Validate phone number
            if len(phone_clean) < 10 or len(phone_clean) > 11:
                return {
                    "response": "Número inválido. Por favor, digite seu WhatsApp com DDD (ex: 11999999999):",
                    "response_type": "phone_validation_error",
                    "session_id": session_id,
                    "collecting_phone": True,
                    "flow_completed": True,
                    "ai_mode": False
                }
            
            # Format phone number
            if len(phone_clean) == 10:
                phone_formatted = f"55{phone_clean[:2]}9{phone_clean[2:]}"
            else:
                phone_formatted = f"55{phone_clean}"
            
            # Update session
            session_data["phone_collected"] = True
            session_data["collecting_phone"] = False
            session_data["ai_mode"] = True
            session_data["phone_number"] = phone_clean
            session_data["phone_formatted"] = phone_formatted
            
            await save_user_session(session_id, session_data)
            
            # Send WhatsApp confirmation and notify lawyers
            await self._send_whatsapp_confirmation_and_notify(session_data, phone_formatted)
            
            confirmation_message = f"✅ Número confirmado: {phone_clean}\n\nSuas informações foram registradas com sucesso! Nossa equipe entrará em contato em breve.\n\nAgora você pode continuar conversando comigo sobre questões jurídicas."
            
            logger.info(f"📱 Phone collected successfully | session={session_id} | phone={phone_clean}")
            
            return {
                "response": confirmation_message,
                "response_type": "phone_collected",
                "session_id": session_id,
                "flow_completed": True,
                "phone_collected": True,
                "collecting_phone": False,
                "ai_mode": True,
                "phone_number": phone_clean
            }
            
        except Exception as e:
            logger.error(f"❌ Error in phone collection: {str(e)}")
            return {
                "response": "Erro ao processar seu número. Vamos continuar! Como posso ajudá-lo?",
                "response_type": "phone_error_fallback",
                "session_id": session_id,
                "flow_completed": True,
                "ai_mode": True,
                "phone_collected": False
            }

    async def _send_whatsapp_confirmation_and_notify(
        self,
        session_data: Dict[str, Any],
        phone_formatted: str
    ):
        """Send WhatsApp confirmation to user and notify lawyers."""
        try:
            lead_data = session_data.get("lead_data", {})
            user_name = lead_data.get("step_1", "Cliente")
            area_of_law = lead_data.get("step_2", "Não informado")
            situation = lead_data.get("step_3", "Não informado")
            
            # Send confirmation to user
            user_message = f"""Olá {user_name}! 👋

Recebemos suas informações e nossa equipe jurídica especializada vai entrar em contato em breve.

📋 Resumo do seu caso:
• Área: {area_of_law}
• Situação: {situation[:100]}{'...' if len(situation) > 100 else ''}

Obrigado por escolher nossos serviços! 🤝"""

            try:
                await baileys_service.send_whatsapp_message(
                    f"{phone_formatted}@s.whatsapp.net",
                    user_message
                )
                logger.info(f"✅ Confirmation sent to user: {phone_formatted}")
            except Exception as e:
                logger.error(f"❌ Error sending user confirmation: {str(e)}")
            
            # Notify lawyers
            try:
                await lawyer_notification_service.notify_lawyers_of_new_lead(
                    lead_name=user_name,
                    lead_phone=session_data.get("phone_number", ""),
                    category=area_of_law,
                    additional_info={
                        "situation": situation,
                        "platform": session_data.get("platform", "web"),
                        "session_id": session_data.get("session_id")
                    }
                )
                logger.info(f"✅ Lawyers notified for lead: {user_name}")
            except Exception as e:
                logger.error(f"❌ Error notifying lawyers: {str(e)}")
                
        except Exception as e:
            logger.error(f"❌ Error in WhatsApp confirmation: {str(e)}")

    async def _handle_ai_conversation(
        self,
        message: str,
        session_id: str,
        session_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle AI conversation after flow completion."""
        try:
            # Try Gemini AI first
            if not self._is_gemini_unavailable():
                try:
                    context = {
                        "name": session_data.get("lead_data", {}).get("step_1"),
                        "area_of_law": session_data.get("lead_data", {}).get("step_2"),
                        "situation": session_data.get("lead_data", {}).get("step_3"),
                        "platform": session_data.get("platform", "web")
                    }
                    
                    ai_response = await ai_orchestrator.generate_response(
                        message, session_id, context
                    )
                    
                    await save_user_session(session_id, session_data)
                    
                    return {
                        "response": ai_response,
                        "response_type": "ai_intelligent",
                        "session_id": session_id,
                        "flow_completed": True,
                        "phone_collected": True,
                        "ai_mode": True,
                        "gemini_available": True
                    }
                    
                except Exception as e:
                    if self._is_quota_error(str(e)):
                        self._mark_gemini_unavailable()
                        logger.warning(f"🚫 Gemini quota exceeded, using fallback")
                    else:
                        logger.error(f"❌ Gemini error: {str(e)}")
            
            # Fallback response
            fallback_response = "Obrigado pela sua mensagem! Nossa equipe já tem suas informações e entrará em contato em breve para dar continuidade ao seu caso."
            
            return {
                "response": fallback_response,
                "response_type": "ai_fallback",
                "session_id": session_id,
                "flow_completed": True,
                "phone_collected": True,
                "ai_mode": True,
                "gemini_available": False
            }
            
        except Exception as e:
            logger.error(f"❌ Error in AI conversation: {str(e)}")
            return {
                "response": "Como posso ajudá-lo?",
                "response_type": "ai_error_fallback",
                "session_id": session_id,
                "ai_mode": True
            }

    def _validate_answer(self, answer: str, step: int) -> bool:
        """Validate user answers based on step."""
        if not answer or len(answer.strip()) < 2:
            return False
        
        if step == 1:  # Name
            return len(answer.split()) >= 2
        elif step == 2:  # Area of law
            return len(answer.strip()) >= 3
        elif step == 3:  # Situation
            return len(answer.strip()) >= 10
        elif step == 4:  # Meeting preference
            return len(answer.strip()) >= 1
        
        return True

    def _is_phone_number(self, text: str) -> bool:
        """Check if text looks like a phone number."""
        phone_clean = re.sub(r'[^\d]', '', text)
        return 10 <= len(phone_clean) <= 13

    def _is_quota_error(self, error_message: str) -> bool:
        """Check if error is related to API quota/rate limits."""
        error_lower = error_message.lower()
        quota_indicators = [
            "429", "quota", "rate limit", "resourceexhausted", 
            "billing", "exceeded", "too many requests"
        ]
        return any(indicator in error_lower for indicator in quota_indicators)

    def _mark_gemini_unavailable(self):
        """Mark Gemini as temporarily unavailable."""
        self.gemini_unavailable_until = datetime.now() + self.gemini_check_interval
        logger.warning(f"🚫 Gemini marked unavailable until {self.gemini_unavailable_until}")

    def _is_gemini_unavailable(self) -> bool:
        """Check if Gemini is currently marked as unavailable."""
        if self.gemini_unavailable_until is None:
            return False
        
        if datetime.now() > self.gemini_unavailable_until:
            self.gemini_unavailable_until = None
            logger.info("✅ Gemini availability restored")
            return False
        
        return True

    async def handle_whatsapp_authorization(self, auth_data: Dict[str, Any]):
        """Handle WhatsApp authorization from button clicks."""
        try:
            session_id = auth_data.get("session_id")
            phone_number = auth_data.get("phone_number")
            source = auth_data.get("source", "whatsapp_button")
            
            logger.info(f"🔗 WhatsApp authorization | session={session_id} | source={source}")
            
            # Create or update session for WhatsApp
            session_data = {
                "session_id": session_id,
                "platform": "whatsapp",
                "current_step": 1,
                "flow_completed": False,
                "collecting_phone": False,
                "phone_collected": False,
                "ai_mode": False,
                "lead_data": {},
                "message_count": 0,
                "phone_number": phone_number,
                "source": source,
                "authorized_at": datetime.now(),
                "created_at": datetime.now(),
                "last_updated": datetime.now()
            }
            
            await save_user_session(session_id, session_data)
            
            # Send initial message to WhatsApp
            welcome_message = "👋 Olá! Bem-vindo ao nosso escritório de advocacia.\n\nVou fazer algumas perguntas para entender melhor seu caso e conectá-lo com nossos advogados especializados.\n\nPara começar, qual é o seu nome completo?"
            
            try:
                await baileys_service.send_whatsapp_message(
                    f"{phone_number}@s.whatsapp.net",
                    welcome_message
                )
                logger.info(f"✅ Welcome message sent to WhatsApp: {phone_number}")
            except Exception as e:
                logger.error(f"❌ Error sending welcome message: {str(e)}")
            
            return {
                "success": True,
                "session_id": session_id,
                "message": "WhatsApp conversation initialized"
            }
            
        except Exception as e:
            logger.error(f"❌ Error in WhatsApp authorization: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    async def handle_phone_number_submission(
        self,
        phone_number: str,
        session_id: str,
        user_name: str = "Cliente"
    ) -> Dict[str, Any]:
        """Handle phone number submission from web platform."""
        try:
            # Get session data
            session_data = await get_user_session(session_id)
            if not session_data:
                return {"success": False, "error": "Session not found"}
            
            # Process phone number
            phone_clean = re.sub(r'[^\d]', '', phone_number)
            if len(phone_clean) == 10:
                phone_formatted = f"55{phone_clean[:2]}9{phone_clean[2:]}"
            else:
                phone_formatted = f"55{phone_clean}"
            
            # Update session
            session_data["phone_collected"] = True
            session_data["phone_number"] = phone_clean
            session_data["phone_formatted"] = phone_formatted
            session_data["ai_mode"] = True
            
            await save_user_session(session_id, session_data)
            
            # Send confirmations and notifications
            await self._send_whatsapp_confirmation_and_notify(session_data, phone_formatted)
            
            return {
                "success": True,
                "phone_number": phone_clean,
                "message": "Phone number processed successfully"
            }
            
        except Exception as e:
            logger.error(f"❌ Error in phone submission: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """Get session context for status checks."""
        try:
            session_data = await get_user_session(session_id)
            if not session_data:
                return {"exists": False}
            
            return {
                "exists": True,
                "session_data": session_data,
                "current_step": session_data.get("current_step"),
                "flow_completed": session_data.get("flow_completed", False),
                "phone_collected": session_data.get("phone_collected", False),
                "ai_mode": session_data.get("ai_mode", False),
                "platform": session_data.get("platform", "unknown")
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting session context: {str(e)}")
            return {"exists": False, "error": str(e)}

    async def reset_session(self, session_id: str) -> Dict[str, Any]:
        """Reset a session for testing purposes."""
        try:
            await save_user_session(session_id, None)  # Delete session
            return {"success": True, "message": "Session reset successfully"}
        except Exception as e:
            logger.error(f"❌ Error resetting session: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_overall_service_status(self) -> Dict[str, Any]:
        """Get overall service status."""
        try:
            firebase_status = await get_firebase_service_status()
            
            return {
                "overall_status": "active" if firebase_status.get("status") == "active" else "degraded",
                "firebase_status": firebase_status,
                "ai_status": {
                    "status": "active" if not self._is_gemini_unavailable() else "quota_exceeded",
                    "gemini_available": not self._is_gemini_unavailable()
                },
                "features": {
                    "structured_flow": True,
                    "phone_collection": True,
                    "whatsapp_integration": True,
                    "lawyer_notifications": True,
                    "ai_fallback": True
                },
                "fallback_mode": self._is_gemini_unavailable(),
                "gemini_available": not self._is_gemini_unavailable()
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting service status: {str(e)}")
            return {
                "overall_status": "error",
                "error": str(e),
                "firebase_status": {"status": "error"},
                "ai_status": {"status": "error"}
            }


# Global orchestrator instance
intelligent_orchestrator = IntelligentHybridOrchestrator()