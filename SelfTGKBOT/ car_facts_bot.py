import logging
import asyncio
import requests
import json
from hashlib import md5
from telegram import Bot
from telegram.error import TelegramError
from config import TELEGRAM_BOT_TOKEN, CHANNEL_ID, OWNER_ID, IOINTELLIGENCE_API_KEY

# Логи
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("car_facts_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


MODELS_API_URL = "https://api.intelligence.io.solutions/api/v1/models"
CHAT_API_URL = "https://api.intelligence.io.solutions/api/v1/chat/completions"

AVAILABLE_MODELS = [
    "microsoft/Phi-3.5-mini-instruct"
]


published_facts = set()

def get_model_list():
    """Получает список доступных моделей"""
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {IOINTELLIGENCE_API_KEY}",  
    }
    try:
        response = requests.get(MODELS_API_URL, headers=headers)
        return [model['id'] for model in response.json() if 'id' in model]
    except Exception as e:
        logger.error(f"Ошибка запроса моделей: {e}")
        return AVAILABLE_MODELS  # Возвращаем дефолтные модели при ошибке

async def generate_unique_fact(model: str, attempt=0):
    """Генерирует уникальный факт с проверкой на повторы"""
    if attempt > 3: 
        raise Exception("Не удалось сгенерировать уникальный факт после 3 попыток")
    
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {IOINTELLIGENCE_API_KEY}",
    }

    prompt = (
        "Придумай уникальный, малоизвестный факт об автомобилях. "
        "Факт должен быть:\n"
        "- Достоверным и проверяемым\n"
        "- Неочевидным для большинства людей\n"
        "- Коротким (1-2 предложения)\n"
        "- Увлекательным\n"
        "- На русском языке\n\n"
        "Важно: факт должен быть действительно уникальным!"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Ты эксперт по автомобильной истории и технологиям"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8 + attempt*0.1,
        "max_tokens": 150
    }

    try:
        response = requests.post(CHAT_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        fact = response.json()['choices'][0]['message']['content'].strip()
        fact_hash = md5(fact.encode()).hexdigest()
        
        if fact_hash in published_facts:
            logger.info(f"Факт повторяется, пробуем снова (попытка {attempt+1})")
            return await generate_unique_fact(model, attempt+1)
            
        published_facts.add(fact_hash)
        return fact
        
    except Exception as e:
        logger.error(f"Ошибка генерации факта: {e}")
        raise

async def send_message(bot: Bot, chat_id: int, text: str):
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except TelegramError as e:
        logger.error(f"Ошибка отправки сообщения: {e}")

async def post_car_fact(bot: Bot, model: str):
    try:
        fact = await generate_unique_fact(model)
        post_text = f"🚗 Автомобильный факт:\n\n{fact}\n\n#авто #факты"
        
        await send_message(bot, CHANNEL_ID, post_text)
        await send_message(
            bot, 
            OWNER_ID,
            f"✅ Успешная публикация\nМодель: {model}\nФакт: {fact}\n"
            f"Всего уникальных фактов: {len(published_facts)}"
        )
    except Exception as e:
        await send_message(bot, OWNER_ID, f"❌ Ошибка: {str(e)}")

async def main():
    """Основной цикл бота"""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    models = get_model_list() or AVAILABLE_MODELS
    
    # Уведомление о запуске
    await send_message(
        bot, 
        OWNER_ID, 
        f"🤖 Бот запущен\nДоступные модели: {', '.join(models)}\n"
        f"Первая модель для теста: {models[0]}"
    )
    
    current_model_index = 0
    while True:
        try:
            model = models[current_model_index]
            await post_car_fact(bot, model)
            
            
        except Exception as e:
            logger.error(f"Ошибка в основном цикле: {e}")
        
        await asyncio.sleep(3*60*60)  # 3 часа

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Фатальная ошибка: {e}")