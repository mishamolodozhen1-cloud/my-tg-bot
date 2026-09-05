import os
import requests
import telebot

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8523492309:AAF1z6AdIrG9sE1BzU_3p7AuRYedOU5edXs"   # ✅ Новый токен
OPENROUTER_API_KEY = "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"

CHAT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
TTS_MODEL = "deepgram/flux-tts:free"
IMAGE_MODEL = "openrouter/free"

TTS_VOICE = "flux-alexis-en"
MAX_HISTORY = 10

bot = telebot.TeleBot(BOT_TOKEN)
user_histories = {}

# ========== ФУНКЦИИ ==========

def chat_with_ai(user_id, user_text):
    history = user_histories.get(user_id, [])
    history.append({"role": "user", "content": user_text})
    if len(history) > MAX_HISTORY * 2:
        history = history[-MAX_HISTORY * 2:]

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": CHAT_MODEL,
        "messages": history,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        reply = data['choices'][0]['message']['content']
        history.append({"role": "assistant", "content": reply})
        user_histories[user_id] = history
        return reply
    except Exception as e:
        print(f"Ошибка чата: {e}")
        return None

def text_to_speech(text):
    url = "https://openrouter.ai/api/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/your_bot",
        "X-OpenRouter-Title": "TTS Bot",
    }
    payload = {
        "model": TTS_MODEL,
        "input": text,
        "voice": TTS_VOICE,
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"TTS ошибка: {e}")
        return None

def generate_image(prompt):
    url = "https://openrouter.ai/api/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data['data'][0]['url']
    except Exception as e:
        print(f"Ошибка генерации изображения: {e}")
        return None

def send_audio(chat_id, text, reply_to=None):
    audio_data = text_to_speech(text)
    if audio_data is None:
        bot.send_message(chat_id, "⚠️ Не удалось озвучить.", reply_to_message_id=reply_to)
        return
    temp = "output.mp3"
    with open(temp, "wb") as f:
        f.write(audio_data)
    try:
        with open(temp, "rb") as f:
            bot.send_audio(chat_id, f, caption="🎧 Озвучка", reply_to_message_id=reply_to)
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка отправки аудио: {e}", reply_to_message_id=reply_to)
    finally:
        if os.path.exists(temp):
            os.remove(temp)

# ========== ОСНОВНОЙ ОБРАБОТЧИК С АВТООПРЕДЕЛЕНИЕМ ==========
@bot.message_handler(func=lambda msg: True)
def handle_message(message):
    user_id = message.from_user.id
    text = message.text.strip()
    if not text:
        return

    # 1. Распознаём запрос на генерацию изображения
    image_keywords = ["нарисуй", "сгенерируй", "изображение", "картинку", "покажи", "сделай фото", "нарисуйте"]
    if any(keyword in text.lower() for keyword in image_keywords):
        prompt = text
        for kw in image_keywords:
            prompt = prompt.lower().replace(kw, "").strip()
        if not prompt:
            prompt = text

        status = bot.reply_to(message, "🎨 Генерирую изображение...")
        image_url = generate_image(prompt)
        if image_url is None:
            bot.edit_message_text("❌ Не удалось сгенерировать. Попробуйте позже.",
                                  chat_id=message.chat.id, message_id=status.message_id)
            return
        try:
            img_data = requests.get(image_url, timeout=30).content
            bot.send_photo(message.chat.id, img_data,
                           caption=f"🖼️ По запросу: {prompt}",
                           reply_to_message_id=message.message_id)
            bot.delete_message(message.chat.id, status.message_id)
        except Exception as e:
            bot.edit_message_text(f"⚠️ Ошибка: {e}",
                                  chat_id=message.chat.id, message_id=status.message_id)
        return

    # 2. Распознаём запрос на озвучку (без ответа ИИ)
    voice_keywords = ["озвучь", "скажи голосом", "прочитай"]
    if any(keyword in text.lower() for keyword in voice_keywords):
        voice_text = text
        for kw in voice_keywords:
            voice_text = voice_text.lower().replace(kw, "").strip()
        if not voice_text:
            voice_text = text
        send_audio(message.chat.id, voice_text, reply_to=message.message_id)
        return

    # 3. Обычный диалог + озвучка ответа
    status = bot.reply_to(message, "💭 Думаю...")
    reply = chat_with_ai(user_id, text)
    if reply is None:
        bot.edit_message_text("❌ Ошибка ИИ. Попробуйте позже.",
                              chat_id=message.chat.id, message_id=status.message_id)
        return

    bot.edit_message_text(f"💬 {reply}",
                          chat_id=message.chat.id, message_id=status.message_id)
    send_audio(message.chat.id, reply, reply_to=message.message_id)

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("✅ Бот запущен (автоопределение: текст/изображение/озвучка).")
    bot.infinity_polling()
