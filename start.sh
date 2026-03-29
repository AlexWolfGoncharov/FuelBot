#!/bin/bash

# FuelBot Quick Start Script
# Швидкий запуск FuelBot в Docker

set -e

echo "🚗 FuelBot - Швидкий запуск в Docker"
echo "======================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Файл .env не знайдено!"
    echo ""
    echo "Будь ласка, створіть .env файл з наступними параметрами:"
    echo ""
    echo "BOT_TOKEN=your_telegram_bot_token"
    echo "GEMINI_API_KEY=your_gemini_api_key"
    echo "ALLOWED_USER_IDS=your_telegram_id"
    echo ""
    echo "Ви можете скопіювати .env.example:"
    echo "  cp .env.example .env"
    echo ""
    exit 1
fi

# Create data directory if it doesn't exist
mkdir -p data
mkdir -p logs

echo "✅ Файл .env знайдено"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не встановлено!"
    echo "Встановіть Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose не встановлено!"
    echo "Встановіть Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "🔨 Збираємо Docker образ..."
docker-compose build

echo ""
echo "🚀 Запускаємо FuelBot..."
docker-compose up -d

echo ""
echo "✅ FuelBot запущено!"
echo ""
echo "📋 Корисні команди:"
echo "  docker-compose logs -f        # Переглянути логи"
echo "  docker-compose restart        # Перезапустити бота"
echo "  docker-compose stop           # Зупинити бота"
echo "  docker-compose down           # Зупинити і видалити контейнер"
echo ""
echo "📊 База даних: ./data/fuel_tracker.db"
echo "📝 Логи: ./logs/"
echo ""
