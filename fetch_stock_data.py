import requests
import time
import datetime
import csv
import os
import collections
import math

# 人福医药的股票代码 (上交所)
STOCK_CODE = 'sh600079'
SINA_API_URL = f'http://hq.sinajs.cn/list={STOCK_CODE}'
HEADERS = {'Referer': 'http://finance.sina.com.cn'}
CSV_FILENAME = 'renfu_stock_data.csv'

class DayTradeAnalyzer:
    def __init__(self, window_size=20):
        # 记录最近N个Tick的价格，用于计算短线均值和标准差
        self.prices = collections.deque(maxlen=window_size)
    
    def get_signal(self, current_price, vwap):
        self.prices.append(current_price)
        
        # 数据太少时先收集
        if len(self.prices) < 10:
            return "⏳ 观察中..."
            
        mean = sum(self.prices) / len(self.prices)
        variance = sum((p - mean) ** 2 for p in self.prices) / len(self.prices)
        std = math.sqrt(variance)
        
        signal = "⚪ 观望持有"
        
        # 1. 计算 VWAP 乖离率 (全天均价基准)
        # 用来判断股价相对于今天真实平均成本是偏高还是偏低
        vwap_bias = 0
        if vwap > 0:
            vwap_bias = (current_price - vwap) / vwap * 100
            
        # 2. 计算 Z-Score (短线布林带)
        # 衡量短期(过去几分钟)股价的突发波动
        z_score = 0
        if std > 0.005:  # 避免分母为0
            z_score = (current_price - mean) / std
            
        # --- 综合判断逻辑 (高抛低吸) ---
        
        if vwap_bias > 1.5 and z_score > 2:
            signal = "🔥 强烈高抛！(短线暴拉且严重跑赢均价)"
        elif vwap_bias < -1.5 and z_score < -2:
            signal = "💰 强烈低吸！(短线急跌且严重跑输均价，具备反弹需求)"
        elif z_score > 2:
            signal = "🔴 建议高抛 (短线冲高，可卖出部分做T，等回落接回)"
        elif z_score < -2:
            signal = "🟢 建议低吸 (短线杀跌，可买入部分做T，等反弹卖出)"
        elif vwap_bias > 2:
            signal = "⚠️ 警惕回落 (处于全天高位区域)"
        elif vwap_bias < -2:
            signal = "👀 关注企稳 (处于全天低位区域，随时可能反弹)"
            
        return signal

def fetch_realtime_data():
    try:
        response = requests.get(SINA_API_URL, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            data_str = response.text
            content = data_str.split('="')[1].split('";')[0]
            if not content:
                print("未获取到数据，可能是非交易时间或代码错误。")
                return None
            
            parts = content.split(',')
            if len(parts) > 30:
                volume = int(parts[8])   # 累计成交股数
                amount = float(parts[9]) # 累计成交金额
                
                # 新浪接口的累积金额/累积股数 即为当日极度精准的 VWAP
                daily_vwap = amount / volume if volume > 0 else 0
                
                stock_data = {
                    'name': parts[0],
                    'open': float(parts[1]),
                    'pre_close': float(parts[2]),
                    'current': float(parts[3]),
                    'high': float(parts[4]),
                    'low': float(parts[5]),
                    'volume': volume,
                    'amount': amount,
                    'vwap': daily_vwap, 
                    'date': parts[30],
                    'time': parts[31]
                }
                return stock_data
    except Exception as e:
        print(f"请求发生异常: {e}")
    return None

def init_csv():
    if not os.path.exists(CSV_FILENAME):
        with open(CSV_FILENAME, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['日期', '时间', '当前价', '开盘价', '最高价', '最低价', '成交额(万)', '涨跌幅(%)', '当日VWAP', '做T信号'])

def main():
    print("========================================")
    print(" 🚀 人福医药 (600079) 日内做T动态监控系统")
    print("========================================")
    print("原理：基于当日VWAP真实平均成本，叠加短线价格瞬时背离率进行高抛低吸提醒。")
    print("按 Ctrl+C 随时停止。\n")
    
    init_csv()
    analyzer = DayTradeAnalyzer(window_size=12) # 过去1分钟(12 * 5秒)的多空情绪

    try:
        while True:
            data = fetch_realtime_data()
            if data and data['current'] > 0:
                change_pct = ((data['current'] - data['pre_close']) / data['pre_close']) * 100
                amount_wan = data['amount'] / 10000
                vwap = data['vwap']
                
                # 获取策略信号
                signal = analyzer.get_signal(data['current'], vwap)
                
                # 彩色终端输出 (根据涨跌幅)
                color = '\033[91m' if change_pct > 0 else '\033[92m'
                reset = '\033[0m'
                
                print(f"[{data['time']}] 最新: {color}{data['current']:.2f}{reset} ({change_pct:.2f}%) | "
                      f"VWAP: {vwap:.2f} | 信号: {signal}")
                
                with open(CSV_FILENAME, mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        data['date'], data['time'], data['current'], data['open'],
                        data['high'], data['low'], round(amount_wan, 2), round(change_pct, 2), 
                        round(vwap, 2), signal
                    ])
                    
            time.sleep(5) 
            
    except KeyboardInterrupt:
        print("\n\n交易监控已停止，历史复盘数据已保存至", CSV_FILENAME)

if __name__ == "__main__":
    main()
