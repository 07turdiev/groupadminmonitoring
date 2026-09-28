# Guruh adminlari monitoringi boti

Telegram guruhdagi savollar sonini va har bir admin nechta savolga javob berganini hisoblaydi,
kunlik / haftalik / oylik hisobot beradi.

## Qanday hisoblanadi

- **Savol** — admin bo'lmagan a'zoning guruhdagi xabari (`QUESTION_MODE=mark` bo'lsa, faqat `?` bor xabarlar).
- **Javob** — admin savolga **reply** qilib yozgan xabari.
- Savolga birinchi reply qilgan admin savolni "yopgan" hisoblanadi (**savollar** ustuni),
  adminning barcha reply xabarlari **javoblar** ustunida.
- O'rtacha javob vaqti — savol yozilgandan birinchi admin reply qilgunicha.
- Adminlar ro'yxati Telegramdan avtomatik olinadi (10 daqiqada yangilanadi). Anonim adminlar "Anonim admin" deb ko'rsatiladi.

## O'rnatish

1. @BotFather da bot yarating, tokenni oling.
2. **Muhim:** @BotFather → `/setprivacy` → botni tanlang → **Disable**. Aks holda bot guruhdagi oddiy xabarlarni ko'rmaydi.
   (Yoki botni guruhga admin qilib qo'shing.)
3. Botni guruhga qo'shing.
4. Serverda:

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # va BOT_TOKEN, SUPER_ADMINS ni to'ldiring
python bot.py
```

## Foydalanish (tugmalar)

Hisobotlarni faqat `.env` dagi `SUPER_ADMINS` ro'yxatidagi foydalanuvchilar ko'ra oladi.
Ular botga shaxsiy chatda `/start` yozadi va pastda tugmalar chiqadi:

| Tugma | Hisobot |
|---|---|
| 📅 Bugun / 📅 Kecha | kunlik |
| 🗓 Joriy hafta / 🗓 O'tgan hafta | haftalik (dushanbadan) |
| 📆 Joriy oy / 📆 O'tgan oy | oylik |
| 🆔 Mening ID | o'z ID si |

- Ro'yxatda yo'q odam `/start` bossa, bot "ruxsat yo'q" deb javob beradi va uning ID sini ko'rsatadi.
  Shu ID ni `SUPER_ADMINS` ga qo'shib, botni qayta ishga tushirsangiz, u ham hisobot ko'ra oladi.
- Guruhda hisobot chiqmaydi, shuning uchun mijozlar uni ko'rmaydi. Guruh ID sini bilish uchun
  belgilangan admin guruhda `/id` yozadi.

## Avtomatik hisobotlar

Har kuni `REPORT_TIME` da (standart 09:00) `REPORT_CHAT_ID` ga (bo'sh bo'lsa — `SUPER_ADMINS` ga) yuboriladi:

- har kuni — kechagi kun hisoboti;
- dushanba — o'tgan hafta hisoboti ham;
- oyning 1-kuni — o'tgan oy hisoboti ham.

Ma'lumotlar `data.db` (SQLite) faylida saqlanadi. Bot faqat guruhga qo'shilgandan keyingi xabarlarni hisoblaydi.
