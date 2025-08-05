# EduBot.ai - Academic Document Generation Bot

## Overview

EduBot.ai is a Telegram bot that generates academic documents using AI technology. The bot creates presentations, independent work papers, and research papers (referats) in multiple languages (Uzbek, Russian, English). Users can request document generation through an intuitive interface, make payments for premium services, and manage their account through the bot.

The system operates on a freemium model where users get one free document generation, after which they need to purchase credits. The bot includes comprehensive admin features for payment management, channel subscription requirements, and user analytics.

## User Preferences

Preferred communication style: Simple, everyday language.

## Recent Changes (August 5, 2025)

✓ Admin ID (5304482470) successfully configured
✓ Enhanced admin panel with comprehensive management buttons:
  - 💳 To'lovlar (Payments management)
  - 📋 Buyurtmalar (Orders management) 
  - 📢 Kanal sozlamalari (Channel settings)
  - 🎟 Promokod boshqaruvi (Promocode management)
  - 👥 Foydalanuvchilar (Users management)
  - 📊 Statistika (Statistics)
  - 📤 Xabar yuborish (Broadcast messages)
  - 💰 Narxlar sozlamalari (Price settings)
  - 🔧 Bot sozlamalari (Bot settings)
  - 🗄 Database boshqaruvi (Database management)

### Latest Fixes (August 5, 2025)
✓ Fixed payment notification layout - Screenshot now appears first, then user info and buttons below
✓ Improved AI text generation with enhanced prompts:
  - Added variety in sentence lengths (5-8, 10-15, 20+ words)
  - Better paragraph transitions with connecting words
  - More professional but readable academic style
  - Practical examples after each main point
  - Increased creativity parameters (temperature=0.8, frequency_penalty=0.5)
✓ Enhanced admin button error handling with try-catch blocks
✓ Bot fully operational and handling Telegram updates correctly

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