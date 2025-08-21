# EduBot.ai - Academic Document Generation Bot

## Overview

EduBot.ai is a Telegram bot that generates academic documents using AI technology. The bot creates presentations, independent work papers, and research papers (referats) in multiple languages (Uzbek, Russian, English). Users can request document generation through an intuitive interface, make payments for premium services, and manage their account through the bot.

The system operates on a freemium model where users get one free document generation, after which they need to purchase credits. The bot includes comprehensive admin features for payment management, channel subscription requirements, and user analytics.

## User Preferences

Preferred communication style: Simple, everyday language.

## Recent Changes (August 21, 2025)

✓ **YANGI TAQDIMOT TIZIMI - To'liq qayta qurildi**:
  - **Batch AI System**: Har 3 slaydga alohida AI so'rov
  - **DALL-E Rasm Generatsiyasi**: Pexels o'rniga professional AI rasmlar
  - **3 Layout Tizimi**:
    - **2,5,8,11... - Bullet Points**: 5 nuqta, har birida 35-40 so'z (175-200 so'z)
    - **3,6,9,12... - Matn + DALL-E Rasm**: 100-120 so'zlik uzluksiz matn + o'ng tomonni to'liq qoplagan rasm
    - **4,7,10,13... - 3 Ustunli**: Mantiqli sarlavhalar bilan har ustunda 50+ so'z

✓ **Professional Content Standards - YANGILANDI**:
  - **Bullet Points**: 70-80 so'z har nuqta (jami 350-400 so'z)
  - **3 Ustunli**: 80 so'z har ustun (jami 240+ so'z)
  - **Turli xil sarlavhalar**: takrorlanmas kategoriyalar
  - **Left alignment**: ikki cheti bir tekis format olib tashlandi

✓ **Visual Improvements**:
  - DALL-E rasmlar o'ng tomonni butunlay qoplash (55% width)
  - Professional taqdimot uchun mos rasm generatsiyasi
  - Matn va rasm o'rtasida optimal balans

✓ **Technical Architecture**:
  - `services/ai_service_new.py` - batch AI generation
  - `services/document_service_new.py` - yangi layout tizimi
  - Xatoliklar va type safety yaxshilandi

### Recent Changes (August 21, 2025)

✓ **YANGI DINAMIK NARX TIZIMI** - Sahifa/Slayd Soniga Qarab:
  - **Taqdimot narxlari**: 10 slayd (5000 som), 15 slayd (7000 som), 20 slayd (10000 som)
  - **Mustaqil ish va Referat**: 10-15 varoq (5000 som), 15-20 varoq (7000 som), 20-25 varoq (10000 som), 25-30 varoq (12000 som)
  - Tugmalarda narxlar ko'rsatiladi: "10 slayd - 5000 som"
  - Balance check sahifa/slayd tanlashdan keyin

✓ **Referat va Mustaqil Ish Uchun Bir Xil Sahifa Sonlari**:
  - Har ikkala hujjat turi uchun 10-15, 15-20, 20-25, 25-30 varoq tanlovlari
  - Bir xil interface va foydalanuvchi tajribasi
  - O'zbek tilida "varoq" terminologiyasi

✓ **Narxlar Ma'lumoti Yordam Bo'limida Yangilandi**:
  - Barcha tillarda (O'zbek, Rus, Ingliz) yangi narx jadvali
  - Har bir hujjat turi uchun batafsil narx ko'rsatilgan
  - Promokod va sozlamalar haqida ma'lumot

### Previous Updates
✓ **Promokod Tizimi Sozlamalarga Ko'chirildi** (August 21, 2025):
  - Hujjat yaratishda halaqit qilmaydi
  - Sozlamalar > Promokod kiritish
  - Bepul hujjat yaratish imkoniyati beradi
  
✓ Admin panel va payment tizimi (August 5, 2025)
✓ AI text generation yaxshilandi  
✓ Bot to'liq ishlamoqda

## System Architecture

### Bot Framework
- **Framework**: aiogram v3 (async Telegram bot framework)
- **Language**: Python with async/await patterns
- **State Management**: FSM (Finite State Machine) for handling multi-step user interactions
- **Middleware System**: Custom middlewares for database access and language handling

### Document Generation Pipeline
- **AI Service**: OpenAI GPT-4o integration for content generation
- **Document Creation**: 
  - PowerPoint presentations using python-pptx
  - Word documents using python-docx
  - Structured content generation with customizable parameters (slide count, page count)
- **File Management**: Local file storage with organized directory structure

### User Management & Authentication
- **Multi-language Support**: Uzbek, Russian, and English with dynamic text translation
- **User States**: Registration, language selection, document preferences
- **Channel Subscription**: Required subscription verification for bot access
- **Admin System**: Role-based access for payment approval and system management

### Payment System
- **Manual Payment Processing**: Screenshot-based payment verification
- **Credit System**: Balance tracking with configurable pricing per document type
- **Freemium Model**: One free document per user, then paid credits
- **Admin Review**: Manual payment approval workflow

### Data Architecture
- **User Profiles**: Telegram ID mapping, language preferences, balance tracking
- **Payment Records**: Transaction history with status tracking
- **Document Orders**: Generation history and user activity logs
- **Channel Management**: Required subscription channels with validation

### Business Logic
- **Pricing Structure**: 
  - Presentations: 3000 som
  - Independent work: 5000 som
  - Referats: 4000 som
- **Document Customization**: Variable slide counts (10-20) and page counts (15-25)
- **Promotional System**: Promocode support for free services

## External Dependencies

### Core Services
- **OpenAI API**: GPT-4o model for content generation and academic writing
- **Telegram Bot API**: Real-time messaging and file transfer via aiogram

### Database & Storage
- **SQLite**: Local database for user data, payments, and system configuration
- **aiosqlite**: Async SQLite adapter for non-blocking database operations

### Document Generation
- **python-pptx**: PowerPoint presentation creation with custom layouts and styling
- **python-docx**: Word document generation with academic formatting
- **aiohttp**: Async HTTP client for external API communications

### Python Libraries
- **aiogram**: Telegram bot framework with FSM support
- **openai**: Official OpenAI Python client
- **asyncio**: Async/await runtime for concurrent operations
- **logging**: Comprehensive system logging and error tracking

### Configuration Management
- **Environment Variables**: Secure API key and configuration management
- **Config System**: Centralized settings for pricing, file paths, and system parameters