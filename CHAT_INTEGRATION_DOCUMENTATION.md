# Chat Integration Documentation - Law Firm Project

## Overview

This document describes the chat integration system for the law firm project, including the fixes made to the conversation flow orchestration and the available endpoints for frontend integration.

## 🔧 Issues Fixed

### 1. Step 0 Problem Resolution

**Problem**: The conversation flow was starting at step 0, causing confusion and skipping the first question.

**Solution**: 
- Modified `orchestration_service.py` to initialize sessions with `current_step: 1` instead of 0
- Updated the flow logic to properly handle the first question display
- Fixed the step validation to ensure proper progression from step 1 → 2 → 3 → 4 → phone collection

**Code Changes**:
```python
# Before (causing step 0 issue)
session_data = {
    "current_step": 0,  # ❌ Wrong - caused skipping first question
}

# After (fixed)
session_data = {
    "current_step": 1,  # ✅ Correct - starts at first question
}
```

### 2. Error Handling Improvements

**Problem**: Chat was showing generic error messages instead of proper conversation flow.

**Solution**:
- Added proper error handling in conversation endpoints
- Improved response validation and fallback mechanisms
- Fixed CORS headers for proper frontend communication

### 3. Frontend Integration Fixes

**Problem**: Frontend wasn't properly connecting to backend endpoints.

**Solution**:
- Fixed API endpoint paths in `index.html`
- Added proper error handling and fallback responses
- Created favicon.ico to eliminate 404 errors
- Improved response parsing and display logic

## 📡 Available API Endpoints

### 1. Conversation Management

#### Start New Conversation
```http
POST /api/v1/conversation/start
Content-Type: application/json
```

**Response**:
```json
{
  "session_id": "uuid-string",
  "response": "Qual é o seu nome completo?",
  "ai_mode": false,
  "flow_completed": false,
  "phone_collected": false
}
```

**Usage Example**:
```javascript
const response = await fetch(`${API_BASE_URL}/api/v1/conversation/start`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' }
});
const data = await response.json();
console.log(data.response); // First question
```

#### Process User Response
```http
POST /api/v1/conversation/respond
Content-Type: application/json

{
  "message": "João Silva",
  "session_id": "uuid-string"
}
```

**Response**:
```json
{
  "session_id": "uuid-string",
  "response": "Em qual área do direito você precisa de ajuda?",
  "ai_mode": false,
  "flow_completed": false,
  "phone_collected": false
}
```

**Usage Example**:
```javascript
const payload = {
  message: userInput,
  session_id: sessionId
};

const response = await fetch(`${API_BASE_URL}/api/v1/conversation/respond`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload)
});
```

#### Get Conversation Status
```http
GET /api/v1/conversation/status/{session_id}
```

**Response**:
```json
{
  "session_id": "uuid-string",
  "platform": "web",
  "status_info": {
    "exists": true,
    "current_step": 2,
    "flow_completed": false,
    "phone_collected": false
  }
}
```

### 2. WhatsApp Integration

#### Authorize WhatsApp Session
```http
POST /api/v1/whatsapp/authorize
Content-Type: application/json

{
  "session_id": "whatsapp_unique_id",
  "phone_number": null,
  "source": "floating_button",
  "user_data": {
    "origem": "Botão Flutuante",
    "site": "m.lima"
  }
}
```

**Response**:
```json
{
  "status": "authorized",
  "session_id": "whatsapp_unique_id",
  "phone_number": null,
  "source": "floating_button",
  "message": "Sessão autorizada",
  "whatsapp_url": "https://wa.me/5511918368812"
}
```

#### Check WhatsApp Authorization
```http
GET /api/v1/whatsapp/check-auth/{phone_number}
```

**Response**:
```json
{
  "phone_number": "5511999999999",
  "authorized": true,
  "action": "RESPOND",
  "session_id": "whatsapp_session_id"
}
```

#### WhatsApp Status
```http
GET /api/v1/whatsapp/status
```

**Response**:
```json
{
  "status": "connected",
  "service": "baileys_whatsapp",
  "connected": true,
  "phone_number": "+5511918368812"
}
```

### 3. System Status

#### Health Check
```http
GET /health
```

**Response**:
```json
{
  "status": "healthy",
  "message": "Law Firm AI Chat Backend is running",
  "services": {
    "fastapi": "active",
    "whatsapp_bot": "connected",
    "firebase": "active"
  }
}
```

## 🔄 Conversation Flow Logic

### Landing Page Flow (Web Platform)

1. **Step 1**: Name collection
   - Question: "Qual é o seu nome completo?"
   - Validation: Minimum 2 words

2. **Step 2**: Legal area
   - Question: "Em qual área do direito você precisa de ajuda?"
   - Options: Penal, Saúde Liminar

3. **Step 3**: Situation description
   - Question: "Descreva brevemente sua situação"
   - Validation: Minimum 10 characters

4. **Step 4**: Meeting preference
   - Question: "Gostaria de agendar uma consulta?"
   - Options: Sim/Não

5. **Phone Collection**: WhatsApp number
   - Question: "Informe seu número de WhatsApp com DDD"
   - Validation: Brazilian phone format (10-11 digits)

6. **Completion**: 
   - Lead data saved to Firebase
   - Lawyers notified via WhatsApp with clickable assignment links
   - User receives confirmation message

### WhatsApp Flow

1. **Authorization**: User clicks WhatsApp button → Pre-authorization created
2. **First Message**: User sends message → Bot responds with structured questions
3. **Same Flow**: Follows the same 4-step process as web
4. **Direct Integration**: No phone collection needed (already on WhatsApp)
5. **Lawyer Handover**: Direct assignment and conversation takeover

## 📱 WhatsApp Button Integration

### Button Types and Triggers

#### 1. Floating WhatsApp Button
```javascript
// Automatically intercepted by chat.js
// Triggers: authorizeWhatsAppSession('floating_button', userData)
```

#### 2. "WhatsApp 24h" Button
```javascript
// Manual integration needed
WhatsAppIntegration.openWhatsApp('whatsapp_24h', {
  origem: 'Botão 24h',
  urgencia: 'alta'
});
```

#### 3. "Talk to Specialist" Button
```javascript
// Manual integration needed
WhatsAppIntegration.openWhatsApp('specialist_button', {
  origem: 'Falar com Especialista',
  tipo: 'consulta_especializada'
});
```

### Integration Code Example

```javascript
// For any WhatsApp button
document.getElementById('your-whatsapp-button').addEventListener('click', function() {
  WhatsAppIntegration.openWhatsApp('button_source', {
    origem: 'Custom Button',
    pagina: window.location.pathname,
    timestamp: new Date().toISOString()
  });
});
```

## 🔀 Platform Differences

### Landing Page Chatbot (Web)
- **Purpose**: Lead collection and qualification
- **Flow**: Structured 4-step questionnaire
- **Completion**: Phone number → WhatsApp notification → Lawyer assignment
- **User Experience**: Chat interface → Phone input → WhatsApp redirect
- **Data Storage**: Complete lead profile in Firebase

### WhatsApp Bot
- **Purpose**: Direct conversation with lawyers
- **Flow**: Same structured questions but in WhatsApp
- **Completion**: Direct lawyer notification and handover
- **User Experience**: Continuous WhatsApp conversation
- **Data Storage**: Same lead profile + WhatsApp conversation history

## 🛠 Frontend Integration Examples

### Basic Chat Implementation

```javascript
// Initialize chat
async function initializeChat() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/conversation/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    
    const data = await response.json();
    
    if (data.session_id) {
      localStorage.setItem('chat_session_id', data.session_id);
    }
    
    if (data.response) {
      displayBotMessage(data.response);
    }
  } catch (error) {
    console.error('Chat initialization failed:', error);
    displayBotMessage('Olá! Como posso ajudá-lo?');
  }
}

// Send message
async function sendMessage(message) {
  const sessionId = localStorage.getItem('chat_session_id');
  
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/conversation/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        session_id: sessionId
      })
    });
    
    const data = await response.json();
    
    if (data.response) {
      displayBotMessage(data.response);
    }
    
    // Handle phone collection completion
    if (data.phone_collected && data.phone_number) {
      // Redirect to WhatsApp or show success message
      handlePhoneCollectionComplete(data);
    }
    
  } catch (error) {
    console.error('Message sending failed:', error);
    displayBotMessage('Desculpe, ocorreu um erro. Tente novamente.');
  }
}
```

### WhatsApp Integration

```javascript
// WhatsApp button click handler
function handleWhatsAppButton(source, additionalData = {}) {
  // Pre-authorize session
  WhatsAppIntegration.openWhatsApp(source, {
    ...additionalData,
    page_url: window.location.href,
    timestamp: new Date().toISOString()
  });
}

// Usage examples
document.getElementById('whatsapp-24h').addEventListener('click', () => {
  handleWhatsAppButton('whatsapp_24h', { urgencia: 'alta' });
});

document.getElementById('specialist-button').addEventListener('click', () => {
  handleWhatsAppButton('specialist_consultation', { tipo: 'especialista' });
});
```

### Error Handling

```javascript
// Comprehensive error handling
async function makeAPICall(endpoint, options = {}) {
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return await response.json();
    
  } catch (error) {
    console.error(`API call failed for ${endpoint}:`, error);
    
    // Return fallback response
    return {
      error: true,
      message: 'Serviço temporariamente indisponível. Tente novamente em alguns minutos.',
      fallback: true
    };
  }
}
```

## 🔍 Testing and Debugging

### Test Endpoints

```bash
# Health check
curl https://law-firm-backend-936902782519-936902782519.us-central1.run.app/health

# Start conversation
curl -X POST https://law-firm-backend-936902782519-936902782519.us-central1.run.app/api/v1/conversation/start \
  -H "Content-Type: application/json"

# Send message
curl -X POST https://law-firm-backend-936902782519-936902782519.us-central1.run.app/api/v1/conversation/respond \
  -H "Content-Type: application/json" \
  -d '{"message": "João Silva", "session_id": "test-session"}'
```

### Debug Tools

```javascript
// Available in browser console
ChatWidget.clearSession();           // Clear chat session
ChatWidget.setBackend('new-url');    // Change backend URL
WhatsAppIntegration.test('debug');   // Test WhatsApp integration
```

## 📋 Summary

The chat integration system now provides:

1. **Fixed Flow Orchestration**: Proper step progression starting from step 1
2. **Dual Platform Support**: Web chat and WhatsApp integration
3. **Comprehensive API**: RESTful endpoints for all chat operations
4. **Error Handling**: Robust fallback mechanisms
5. **Lead Management**: Automatic lawyer notifications with assignment links
6. **Session Management**: Persistent conversation state across platforms

The system is ready for frontend integration with clear endpoints, proper error handling, and comprehensive documentation for the development team.