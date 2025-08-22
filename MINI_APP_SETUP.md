# Telegram Mini App Setup Instructions

## MUHIM: BotFather orqali Web App URL sozlash

Telegram Mini App ishlashi uchun **BotFather** orqali Web App URL sozlash SHART!

### Qadamlar:

1. **Telegram da @BotFather ga boring**

2. **Botingizni tanlang:**
   ```
   /mybots
   @Hshjdjbot ni tanlang
   ```

3. **Bot Settings → Menu Button:**
   ```
   Bot Settings
   Menu Button
   ```

4. **Web App URL kiriting:**
   ```
   https://ff8081b2-d953-40bb-8e2f-f5970fbed535.eval-code.replit.app/webapp/
   ```

5. **Menu Button matnini kiriting:**
   ```
   📊 Taqdimot yaratish
   ```

## ALTERNATIV: Inline Mode orqali

Agar Menu Button ishlamasa:

1. **BotFather da:**
   ```
   /setinline
   @Hshjdjbot ni tanlang
   ```

2. **Inline placeholder text kiriting:**
   ```
   Taqdimot yaratish...
   ```

## Test qilish:

1. Botga boring
2. Matn kiritish maydonida **Menu Button** paydo bo'lishi kerak
3. Uni bosing - Web App ochilishi kerak
4. Form to'ldiring va "Taqdimot yaratish" bosing
5. Bot web app data ni qabul qilishi kerak

## Muammolar yechimi:

### Agar Menu Button ko'rinmasa:
- Telegram ni qayta ishga tushiring
- Bot chatini o'chirib, qayta /start qiling

### Agar Web App ochilmasa:
- URL to'g'riligini tekshiring
- HTTPS protokol ishlatilganini tekshiring
- Web App server ishlayotganini tekshiring (port 5000)

### Agar data kelmasa:
- Web App da `tg.sendData()` chaqirilganini tekshiring
- Bot handler da `F.web_app_data` filter borligini tekshiring

## Current Status:

❌ BotFather da Web App URL sozlanmagan
✅ Web App server ishlayapti
✅ Bot handler tayyor
✅ Web App HTML tayyor

**KERAKLI HARAKAT: BotFather da Web App URL sozlash!**