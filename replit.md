# EduBot.ai - Academic Document Generation Bot

## Overview
EduBot.ai is a Telegram bot that generates academic documents such as presentations, independent work papers, and research papers (referats) in multiple languages (Uzbek, Russian, English) using AI technology. It operates on a freemium model, offering one free document generation before requiring users to purchase credits. The project aims to provide an intuitive interface for document generation, payment processing, and account management, alongside comprehensive admin features for managing payments, channel subscriptions, and user analytics.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Bot Framework
The bot is built with `aiogram v3`, utilizing Python with async/await patterns for an asynchronous Telegram bot framework. State management is handled by FSM (Finite State Machine) for multi-step user interactions, complemented by custom middlewares for database access and language handling.

### Document Generation Pipeline
AI-driven content generation is powered by OpenAI GPT-4o. Documents are created using `python-pptx` for PowerPoint presentations and `python-docx` for Word documents, supporting structured content generation with customizable parameters like slide and page counts. Files are stored locally in an organized directory structure. The system supports document language selection, author name inclusion, and an optional plan slide for presentations.

### User Management & Authentication
The system features multi-language support (Uzbek, Russian, English) with dynamic text translation. It manages user states, including registration, language selection, and document preferences. Bot access requires channel subscription verification. An admin system provides role-based access for payment approval and system management. A referral system allows users to earn bonuses by inviting new users.

### Payment System
EduBot.ai employs a manual payment processing system where users submit screenshots for verification. A credit-based system tracks user balances, with configurable pricing per document type. The freemium model offers one free document, followed by paid services. A dynamic pricing model adjusts costs based on the number of pages/slides, clearly displayed on buttons. Promocode support is also integrated.

### Data Architecture
User profiles include Telegram ID mapping, language preferences, and balance tracking. The system maintains records for payment transactions, document orders, and user activity logs. Channel management tracks required subscription channels and validates user memberships. Input sanitization and length limitations are implemented for security.

### UI/UX Decisions
The template selection system provides 20 professional background templates displayed in a single 4x5 grid image with a compact inline keyboard. Presentation formats are highly customized, including specific slide layouts for bullet points, text with DALL-E images, and multi-column designs. "Thank you" slides and optional bibliography slides are supported.

## External Dependencies

### Core Services
- **DeepSeek API** (via OpenRouter): Utilized for DeepSeek v3.2 content generation and academic writing.
- **Together AI**: Used for FLUX.1-schnell image generation in presentations.
- **Telegram Bot API**: Facilitates real-time messaging and file transfers.

### Database & Storage
- **SQLite**: Local database for storing user data, payment information, and system configurations.
- **aiosqlite**: Asynchronous SQLite adapter for non-blocking database operations.

### Document Generation
- **python-pptx**: For creating and customizing PowerPoint presentations.
- **python-docx**: For generating Word documents with academic formatting.
- **aiohttp**: Used as an asynchronous HTTP client for external API communications.

### Python Libraries
- **aiogram**: The core framework for Telegram bot development, including FSM support.
- **openai**: Official Python client for interacting with OpenAI services.
- **asyncio**: Provides the asynchronous runtime for concurrent operations.
- **logging**: For comprehensive system logging and error tracking.

### Configuration Management
- **Environment Variables**: For secure management of API keys and configuration.
- **Config System**: Centralized settings for pricing, file paths, and system parameters.