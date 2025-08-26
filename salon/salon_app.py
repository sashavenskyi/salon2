# -*- coding: utf-8 -*-
"""
Created on Tue Aug 26 13:10:38 2025

@author: olve
"""

import streamlit as st
import pandas as pd
from telethon import TelegramClient, events
import re
from datetime import datetime
import asyncio
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import os

# --- Налаштування Telegram API ---
# Замініть ці дані на ваші!
API_ID = 28827902
API_HASH = '570a58b3196f392d2c754ff123c9929f'
CHANNEL_ID = -4914800011

# --- Функції для парсингу та аналізу даних ---
def parse_daily_report(report_text):
    """
    Парсить щоденний звіт за наданим шаблоном і повертає DataFrame.
    """
    date_match = re.search(r'Звіт за (.+)', report_text)
    report_date = datetime.strptime(date_match.group(1).strip(), '%d.%m.%Y').date() if date_match else None
    
    lines = report_text.strip().split('\n')
    data = []
    
    section = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "Клієнти та послуги:" in line:
            section = "services"
        elif "Додаткові продажі:" in line:
            section = "additional_sales"
        elif "Витрати:" in line:
            section = "expenses"
        
        if section == "services" and re.match(r'^\d+\.', line):
            current_entry = {'Date': report_date, 'Section': 'Service'}
            lines_slice = lines[lines.index(line):]
            for sub_line in lines_slice:
                if "Ім'я:" in sub_line:
                    current_entry['Client'] = sub_line.split(":", 1)[1].strip()
                elif "Майстер:" in sub_line:
                    current_entry['Master'] = sub_line.split(":", 1)[1].strip()
                elif "Послуга:" in sub_line:
                    current_entry['Service'] = sub_line.split(":", 1)[1].strip()
                elif "Оплата:" in sub_line:
                    current_entry['Revenue'] = int(re.search(r'(\d+)', sub_line).group(1))
                elif "Тип оплати:" in sub_line:
                    current_entry['PaymentMethod'] = sub_line.split(":", 1)[1].strip()
                    break
            data.append(current_entry)
        
        elif section == "additional_sales" and line.startswith("- Продаж:"):
            current_entry = {'Date': report_date, 'Section': 'Additional Sale'}
            current_entry['Service'] = line.split(":", 1)[1].strip()
            lines_slice = lines[lines.index(line)+1:]
            for sub_line in lines_slice:
                if "Оплата:" in sub_line:
                    current_entry['Revenue'] = int(re.search(r'(\d+)', sub_line).group(1))
                elif "Тип оплати:" in sub_line:
                    current_entry['PaymentMethod'] = sub_line.split(":", 1)[1].strip()
                    data.append(current_entry)
                    break
    
    df = pd.DataFrame(data)
    df['Admin'] = 'Невизначений' 
    return df

def generate_monthly_report(all_reports_df):
    """
    Генерує місячний звіт на основі об'єднаних даних.
    """
    if all_reports_df.empty:
        st.warning("Немає даних для генерації звіту.")
        return None
    
    all_reports_df['Date'] = pd.to_datetime(all_reports_df['Date'])
    monthly_revenue_df = all_reports_df[all_reports_df['PaymentMethod'] != 'Курс']
    total_monthly_revenue = monthly_revenue_df['Revenue'].sum()
    revenue_by_master = monthly_revenue_df.groupby('Master')['Revenue'].sum().sort_values(ascending=False)
    revenue_by_service = monthly_revenue_df.groupby('Service')['Revenue'].sum().sort_values(ascending=False).head(5)
    revenue_by_admin = monthly_revenue_df.groupby('Admin')['Revenue'].sum().sort_values(ascending=False)
    revenue_by_payment_method = monthly_revenue_df.groupby('PaymentMethod')['Revenue'].sum()

    def create_chart(data, title, type='bar'):
        plt.figure(figsize=(10, 6))
        if type == 'bar':
            sns.barplot(x=data.index, y=data.values, palette='viridis')
        else:
            plt.pie(data.values, labels=data.index, autopct='%1.1f%%', startangle=90, colors=sns.color_palette('pastel'))
        plt.title(title)
        plt.xlabel('Категорія')
        plt.ylabel('Виручка (грн)')
        plt.xticks(rotation=45)
        plt.tight_layout()
        img_buffer = BytesIO()
        plt.savefig(img_buffer, format='png')
        img_buffer.seek(0)
        plt.close()
        return img_buffer

    return {
        "Загальна виручка": total_monthly_revenue,
        "Виручка по майстрах": revenue_by_master,
        "Виручка по послугах": revenue_by_service,
        "Виручка по адміністраторах": revenue_by_admin,
        "Графік по майстрах": create_chart(revenue_by_master, 'Виручка за місяць по майстрах'),
        "Графік по послугах": create_chart(revenue_by_service, 'Топ-5 найпопулярніших послуг'),
        "Графік оплати": create_chart(revenue_by_payment_method, 'Розподіл оплати', type='pie')
    }

# --- Інтерфейс програми Streamlit ---
st.set_page_config(page_title="Аналіз даних по салону Venska Easy Body Луцьк", layout="wide")
st.title("📊 Аналіз даних по салону Venska Easy Body Луцьк")

st.info("Натисніть 'Підключитися до Telegram', щоб почати збір звітів. Дані будуть зберігатися у файлі 'all_reports.csv'.")

if 'telegram_client' not in st.session_state:
    st.session_state.telegram_client = None

async def start_telegram_session():
    if not st.session_state.telegram_client:
        try:
            client = TelegramClient('session_name', API_ID, API_HASH)
            await client.start()
            st.session_state.telegram_client = client
            st.success("Підключено до Telegram! Чекаю на нові звіти.")
            
            @client.on(events.NewMessage(chats=CHANNEL_ID))
            async def new_message_handler(event):
                if "Звіт за" in event.message.text:
                    try:
                        daily_df = parse_daily_report(event.message.text)
                        with open('all_reports.csv', 'a', encoding='utf-8') as f:
                            daily_df.to_csv(f, header=f.tell()==0, index=False)
                    except Exception as e:
                        st.error(f"Помилка при обробці звіту: {e}")
            await client.run_until_disconnected()
        except Exception as e:
            st.error(f"Не вдалося підключитися до Telegram: {e}")


if st.button("Підключитися до Telegram"):
    asyncio.run(start_telegram_session())

if st.button("Створити місячний звіт"):
    if 'all_reports.csv' not in os.listdir():
        st.error("Файл 'all_reports.csv' не знайдено.")
    else:
        try:
            all_reports_df = pd.read_csv('all_reports.csv')
            report = generate_monthly_report(all_reports_df)
            if report:
                st.header("Підсумковий місячний звіт")
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("💰 Загальна виручка за місяць")
                    st.metric(label="Загальна сума", value=f"{report['Загальна виручка']:,} грн".replace(",", " "))
                with col2:
                    st.subheader("Розподіл оплати")
                    st.image(report['Графік оплати'], caption='Розподіл оплати (готівка/карта)')
                st.markdown("---")
                st.subheader("Виручка за майстрами")
                st.dataframe(report['Виручка по майстрах'])
                st.image(report['Графік по майстрах'], caption='Розподіл виручки по майстрах')
                st.markdown("---")
                st.subheader("Найпопулярніші послуги")
                st.dataframe(report['Виручка по послугах'])
                st.image(report['Графік по послугах'], caption='Топ-5 найпопулярніших послуг')
        except Exception as e:
            st.error(f"Виникла помилка під час обробки даних: {e}")