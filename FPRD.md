## AI Assistant
# 🎯 Cursor 에이전트용 암호화폐 백테스트 시각화 도구 상세 설계서
## 📋 프로젝트 개요
**목적**: Python 기반 암호화폐 터틀 트레이딩 백테스트 결과를 웹 인터페이스로 시각화 **기존 시스템**: Python + SQLite 기반 백테스트 엔진 **목표**: React 기반 대시보드로 백테스트 결과를 차트와 텍스트로 표시
## 🏗️ 시스템 아키텍처``` 
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   React Frontend│◄──►│  Python API     │◄──►│  백테스트 엔진   │
│   (시각화)       │    │  (FastAPI)      │    │  (기존 코드)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
  - Chart.js/D3.js         - REST API            - strategy.py
  - 설정 입력 폼            - JSON 응답            - backtest.py  
  - 결과 테이블             - CORS 설정            - SQLite DB
```

📁 프로젝트 구조``` 
trading-dashboard/
├── backend/
│   ├── app.py                 # FastAPI 메인 서버
│   ├── backtest_runner.py     # 백테스트 실행 래퍼
│   ├── models/
│   │   ├── config_model.py    # 설정 데이터 모델
│   │   └── result_model.py    # 결과 데이터 모델
│   └── requirements.txt
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ConfigPanel.jsx      # 설정 입력
│   │   │   ├── ChartSection.jsx     # 차트 영역
│   │   │   ├── ResultsPanel.jsx     # 결과 표시
│   │   │   └── MetricsDisplay.jsx   # 성과지표
│   │   ├── services/
│   │   │   └── api.js              # API 통신
│   │   ├── utils/
│   │   │   └── chartConfig.js      # 차트 설정
│   │   ├── App.jsx
│   │   └── index.js
│   ├── package.json
│   └── tailwind.config.js
└── README.md
```

🔧 백엔드 API 설계
주요 엔드포인트``` python
# app.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sys
import os

# 기존 백테스트 모듈 임포트를 위한 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'zillion'))

app = FastAPI(title="Trading Backtest API")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/backtest")
async def run_backtest(config: BacktestConfig):
    """백테스트 실행 및 결과 반환"""
    
@app.get("/api/default-config")
async def get_default_config():
    """기본 설정값 반환"""
    
@app.get("/api/available-tickers")
async def get_tickers():
    """사용 가능한 거래 종목 목록"""
```

데이터 모델``` python
# models/config_model.py
from pydantic import BaseModel
from typing import Optional

class BacktestConfig(BaseModel):
    # 기본 설정
    ticker: str = "XRP/KRW"
    timeframe: str = "1h"
    initial_capital: float = 3_000_000.0
    
    # 터틀 전략 설정
    turtle_entry_period: int = 20
    turtle_atr_period: int = 20
    turtle_risk_rate: float = 1.0
    turtle_max_units: int = 4
    turtle_trailing_multiplier: float = 2.0
    
    # 백테스트 기간
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    
    # 옵션
    print_all_trades: bool = False
    print_monthly: bool = True

# models/result_model.py
class BacktestResult(BaseModel):
    # 차트 데이터
    chart_data: dict
    # 성과 지표
    metrics: dict
    # 거래 내역
    trades: list
    # 로그 텍스트
    logs: list
    # 실행 시간
    execution_time: float
```

백테스트 실행 래퍼``` python
# backtest_runner.py
import subprocess
import json
import tempfile
import os
from models.config_model import BacktestConfig

class BacktestRunner:
    def __init__(self):
        self.zillion_path = "../zillion"
    
    def run_backtest(self, config: BacktestConfig) -> dict:
        """
        기존 백테스트 코드를 실행하고 결과를 파싱
        """
        # 1. 임시 설정 파일 생성
        temp_config = self._create_temp_config(config)
        
        # 2. 백테스트 실행
        result = subprocess.run([
            "python", "-m", "test.backtest"
        ], 
        cwd=self.zillion_path,
        capture_output=True,
        text=True,
        env={**os.environ, "TEMP_CONFIG": temp_config}
        )
        
        # 3. 결과 파싱
        return self._parse_output(result.stdout, result.stderr)
    
    def _create_temp_config(self, config: BacktestConfig) -> str:
        """설정을 임시 파일로 저장"""
        pass
    
    def _parse_output(self, stdout: str, stderr: str) -> dict:
        """백테스트 출력을 파싱해서 구조화된 데이터로 변환"""
        pass
```

🎨 프론트엔드 설계
메인 컴포넌트 구조``` jsx
// App.jsx
import React, { useState } from 'react';
import ConfigPanel from './components/ConfigPanel';
import ChartSection from './components/ChartSection';
import ResultsPanel from './components/ResultsPanel';
import { runBacktest, getDefaultConfig } from './services/api';

function App() {
  const [config, setConfig] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleRunBacktest = async (backtestConfig) => {
    setLoading(true);
    try {
      const result = await runBacktest(backtestConfig);
      setResults(result);
    } catch (error) {
      console.error('백테스트 실행 실패:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* 헤더 */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <h1 className="text-3xl font-bold text-gray-900">
            🐢 터틀 트레이딩 백테스트 대시보드
          </h1>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {/* 설정 패널 */}
        <ConfigPanel onRunBacktest={handleRunBacktest} loading={loading} />
        
        {/* 결과 영역 */}
        {results && (
          <>
            <ChartSection data={results.chart_data} />
            <ResultsPanel 
              metrics={results.metrics}
              trades={results.trades}
              logs={results.logs}
            />
          </>
        )}
      </main>
    </div>
  );
}

export default App;
```

설정 패널 컴포넌트``` jsx
// components/ConfigPanel.jsx
import React, { useState, useEffect } from 'react';

const ConfigPanel = ({ onRunBacktest, loading }) => {
  const [config, setConfig] = useState({
    ticker: "XRP/KRW",
    timeframe: "1h",
    initial_capital: 3000000,
    turtle_entry_period: 20,
    turtle_atr_period: 20,
    turtle_risk_rate: 1.0,
    turtle_max_units: 4,
    turtle_trailing_multiplier: 2.0,
    print_monthly: true
  });

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-xl font-semibold mb-4">⚙️ 백테스트 설정</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* 기본 설정 */}
        <div>
          <h3 className="font-medium mb-3">기본 설정</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">거래 종목</label>
              <select 
                value={config.ticker}
                onChange={(e) => setConfig({...config, ticker: e.target.value})}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
              >
                <option value="XRP/KRW">XRP/KRW</option>
                <option value="BTC/KRW">BTC/KRW</option>
                <option value="ETH/KRW">ETH/KRW</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700">시간봉</label>
              <select 
                value={config.timeframe}
                onChange={(e) => setConfig({...config, timeframe: e.target.value})}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
              >
                <option value="1h">1시간</option>
                <option value="4h">4시간</option>
                <option value="1d">1일</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700">초기 자본</label>
              <input
                type="number"
                value={config.initial_capital}
                onChange={(e) => setConfig({...config, initial_capital: Number(e.target.value)})}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
              />
            </div>
          </div>
        </div>

        {/* 터틀 전략 설정 */}
        <div>
          <h3 className="font-medium mb-3">터틀 전략</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-700">진입 기간</label>
              <input
                type="number"
                value={config.turtle_entry_period}
                onChange={(e) => setConfig({...config, turtle_entry_period: Number(e.target.value)})}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700">ATR 기간</label>
              <input
                type="number"
                value={config.turtle_atr_period}
                onChange={(e) => setConfig({...config, turtle_atr_period: Number(e.target.value)})}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700">리스크 비율 (%)</label>
              <input
                type="number"
                step="0.1"
                value={config.turtle_risk_rate}
                onChange={(e) => setConfig({...config, turtle_risk_rate: Number(e.target.value)})}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
              />
            </div>
          </div>
        </div>

        {/* 실행 옵션 */}
        <div>
          <h3 className="font-medium mb-3">실행 옵션</h3>
          <div className="space-y-3">
            <div>
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={config.print_monthly}
                  onChange={(e) => setConfig({...config, print_monthly: e.target.checked})}
                  className="rounded border-gray-300"
                />
                <span className="ml-2 text-sm text-gray-700">월별 수익률 표시</span>
              </label>
            </div>
          </div>
          
          <button
            onClick={() => onRunBacktest(config)}
            disabled={loading}
            className="mt-4 w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-2 px-4 rounded-md transition-colors"
          >
            {loading ? '실행 중...' : '🚀 백테스트 실행'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfigPanel;
```

차트 섹션 컴포넌트``` jsx
// components/ChartSection.jsx
import React from 'react';
import { Line, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend
);

const ChartSection = ({ data }) => {
  // 수익률 곡선 차트 설정
  const equityChartData = {
    labels: data.dates,
    datasets: [
      {
        label: '누적 수익률',
        data: data.equity_curve,
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        tension: 0.1,
      }
    ]
  };

  // 월별 수익률 차트 설정
  const monthlyReturnsData = {
    labels: data.monthly_labels,
    datasets: [
      {
        label: '월별 수익률 (%)',
        data: data.monthly_returns,
        backgroundColor: data.monthly_returns.map(val => val >= 0 ? 'rgba(34, 197, 94, 0.8)' : 'rgba(239, 68, 68, 0.8)'),
      }
    ]
  };

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top',
      },
    },
    scales: {
      y: {
        beginAtZero: false,
      }
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-xl font-semibold mb-4">📈 백테스트 차트</h2>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 수익률 곡선 */}
        <div>
          <h3 className="text-lg font-medium mb-3">누적 수익률</h3>
          <div className="h-64">
            <Line data={equityChartData} options={chartOptions} />
          </div>
        </div>

        {/* 월별 수익률 */}
        <div>
          <h3 className="text-lg font-medium mb-3">월별 수익률</h3>
          <div className="h-64">
            <Bar data={monthlyReturnsData} options={chartOptions} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChartSection;
```

결과 패널 컴포넌트``` jsx
// components/ResultsPanel.jsx
import React, { useState } from 'react';

const ResultsPanel = ({ metrics, trades, logs }) => {
  const [activeTab, setActiveTab] = useState('metrics');

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {[
            { id: 'metrics', name: '📊 성과지표', count: null },
            { id: 'trades', name: '💰 거래내역', count: trades?.length },
            { id: 'logs', name: '📝 실행로그', count: logs?.length }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`py-2 px-1 border-b-2 font-medium text-sm ${
                activeTab === tab.id
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.name}
              {tab.count && <span className="ml-2 text-xs bg-gray-100 rounded-full px-2 py-1">{tab.count}</span>}
            </button>
          ))}
        </nav>
      </div>

      <div className="mt-6">
        {/* 성과지표 탭 */}
        {activeTab === 'metrics' && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(metrics).map(([key, value]) => (
              <div key={key} className="bg-gray-50 rounded-lg p-4">
                <dt className="text-sm font-medium text-gray-500">{key}</dt>
                <dd className="mt-1 text-2xl font-semibold text-gray-900">
                  {typeof value === 'number' ? 
                    (key.includes('수익률') || key.includes('%') ? `${value.toFixed(2)}%` : value.toLocaleString()) 
                    : value
                  }
                </dd>
              </div>
            ))}
          </div>
        )}

        {/* 거래내역 탭 */}
        {activeTab === 'trades' && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">날짜</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">구분</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">가격</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">수량</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">수익률</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">손익</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {trades?.map((trade, index) => (
                  <tr key={index}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{trade.date}</td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                        trade.action === 'buy' ? 'bg-blue-100 text-blue-800' : 'bg-red-100 text-red-800'
                      }`}>
                        {trade.action === 'buy' ? '매수' : '매도'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{trade.price?.toLocaleString()}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{trade.amount}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {trade.profit_rate && (
                        <span className={trade.profit_rate >= 0 ? 'text-green-600' : 'text-red-600'}>
                          {trade.profit_rate.toFixed(2)}%
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      {trade.pnl && (
                        <span className={trade.pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
                          {trade.pnl.toLocaleString()}원
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 로그 탭 */}
        {activeTab === 'logs' && (
          <div className="bg-gray-900 text-green-400 p-4 rounded-lg font-mono text-sm max-h-96 overflow-y-auto">
            {logs?.map((log, index) => (
              <div key={index} className="mb-1">{log}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultsPanel;
```

API 서비스``` javascript
// services/api.js
const API_BASE_URL = 'http://localhost:8000';

export const runBacktest = async (config) => {
  const response = await fetch(`${API_BASE_URL}/api/backtest`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    throw new Error('백테스트 실행 실패');
  }

  return response.json();
};

export const getDefaultConfig = async () => {
  const response = await fetch(`${API_BASE_URL}/api/default-config`);
  return response.json();
};

export const getAvailableTickers = async () => {
  const response = await fetch(`${API_BASE_URL}/api/available-tickers`);
  return response.json();
};
```

🚀 구현 단계
Phase 1: 기본 구조 (1-2일)
FastAPI 백엔드 기본 구조 생성
React 프론트엔드 기본 레이아웃
설정 입력 폼 구현
기본 API 연동
Phase 2: 백테스트 연동 (2-3일)
기존 백테스트 코드와 API 연동
결과 데이터 파싱 및 구조화
에러 처리 및 로딩 상태 관리
Phase 3: 시각화 (2-3일)
Chart.js를 이용한 기본 차트 구현
수익률 곡선, 월별 수익률 차트
반응형 디자인 적용
Phase 4: 고도화 (1-2일)
결과 테이블 및 로그 표시
내보내기 기능 (CSV, PDF)
다크모드, 테마 지원
📦 필요한 패키지
백엔드 (requirements.txt)``` 
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
python-multipart==0.0.6
```

프론트엔드 (package.json)``` json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "chart.js": "^4.4.0",
    "react-chartjs-2": "^5.2.0",
    "@tailwindcss/forms": "^0.5.7"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.0.3",
    "vite": "^4.4.5",
    "tailwindcss": "^3.3.0",
    "autoprefixer": "^10.4.14",
    "postcss": "^8.4.24"
  }
}
```

이 설계서를 바탕으로 Cursor 에이전트가 단계적으로 구현할 수 있습니다! 🎯

## 나
FPRD.md파일로 만들어서 프로젝트 루트에 놔줘

## AI Assistant

프로젝트 루트에 FPRD.md (Frontend Project Requirements Document) 파일을 생성하겠습니다.``` markdown

# 🎯 Frontend Project Requirements Document (FPRD)
# 암호화폐 터틀 트레이딩 백테스트 시각화 도구

## 📋 프로젝트 개요

**프로젝트명**: Trading Dashboard - 터틀 트레이딩 백테스트 시각화 도구  
**목적**: Python 기반 암호화폐 터틀 트레이딩 백테스트 결과를 웹 인터페이스로 시각화  
**기존 시스템**: Python + SQLite 기반 백테스트 엔진 (zillion 프로젝트)  
**목표**: React 기반 대시보드로 백테스트 결과를 차트와 텍스트로 표시

## 🏗️ 시스템 아키텍처
```

┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ │ React Frontend│◄──►│ Python API │◄──►│ 백테스트 엔진 │ │ (시각화) │ │ (FastAPI) │ │ (기존 zillion) │ └─────────────────┘ └─────────────────┘ └─────────────────┘ │ │ │ ▼ ▼ ▼
Chart.js/D3.js - REST API - strategy.py
설정 입력 폼 - JSON 응답 - backtest.py
결과 테이블 - CORS 설정 - SQLite DB``` 

## 📁 프로젝트 구조
```

trading-dashboard/ ├── backend/ │ ├── app.py # FastAPI 메인 서버 │ ├── backtest_runner.py # 백테스트 실행 래퍼 │ ├── models/ │ │ ├── config_model.py # 설정 데이터 모델 │ │ └── result_model.py # 결과 데이터 모델 │ └── requirements.txt ├── frontend/ │ ├── public/ │ │ ├── index.html │ │ └── favicon.ico │ ├── src/ │ │ ├── components/ │ │ │ ├── ConfigPanel.jsx # 설정 입력 패널 │ │ │ ├── ChartSection.jsx # 차트 영역 │ │ │ ├── ResultsPanel.jsx # 결과 표시 패널 │ │ │ ├── MetricsDisplay.jsx # 성과지표 표시 │ │ │ ├── TradeTable.jsx # 거래내역 테이블 │ │ │ └── LogViewer.jsx # 로그 뷰어 │ │ ├── services/ │ │ │ └── api.js # API 통신 서비스 │ │ ├── utils/ │ │ │ ├── chartConfig.js # 차트 설정 유틸 │ │ │ └── formatters.js # 데이터 포맷팅 │ │ ├── App.jsx # 메인 앱 컴포넌트 │ │ ├── App.css # 스타일 │ │ └── index.js # 앱 진입점 │ ├── package.json │ └── tailwind.config.js # Tailwind CSS 설정 └── README.md``` 

## 🔧 백엔드 API 설계

### 주요 엔드포인트

#### 1. 백테스트 실행
```

http POST /api/backtest Content-Type: application/json
{ "ticker": "XRP/KRW", "timeframe": "1h", "initial_capital": 3000000.0, "turtle_entry_period": 20, "turtle_atr_period": 20, "turtle_risk_rate": 1.0, "turtle_max_units": 4, "turtle_trailing_multiplier": 2.0, "start_date": "2024-01-01", "end_date": "2024-12-31", "print_monthly": true, "print_all_trades": false }``` 

**응답 구조:**
```

json { "success": true, "execution_time": 15.43, "chart_data": { "dates": ["2024-01-01", "2024-01-02", ...], "equity_curve": [3000000, 3015000, 3021000, ...], "balance_history": [3000000, 2850000, 2900000, ...], "monthly_labels": ["2024-01", "2024-02", ...], "monthly_returns": [2.5, -1.2, 4.8, ...], "drawdown_curve": [0, -1.5, -2.1, ...] }, "metrics": { "총수익률": 15.2, "연환산수익률": 18.5, "최대낙폭": -8.3, "샤프비율": 1.42, "승률": 68.5, "총거래횟수": 45, "평균보유기간": 2.3, "최대수익거래": 12.5, "최대손실거래": -4.2 }, "trades":   , "logs":    }latex_unknown_taglatex_unknown_tag``` 

#### 2. 기본 설정 조회
```

http GET /api/default-config
Response: { "ticker": "XRP/KRW", "timeframe": "1h", "initial_capital": 3000000.0, "turtle_entry_period": 20, "turtle_atr_period": 20, "turtle_risk_rate": 1.0, "turtle_max_units": 4, "turtle_trailing_multiplier": 2.0, "print_monthly": true }``` 

#### 3. 사용가능한 거래종목 조회
```

http GET /api/available-tickers
Response: { "tickers": }``` 

### 백엔드 주요 파일

#### app.py (FastAPI 메인 서버)
```

python from fastapi import FastAPI, HTTPException from fastapi.middleware.cors import CORSMiddleware from models.config_model import BacktestConfig from models.result_model import BacktestResult from backtest_runner import BacktestRunner import sys import os
기존 zillion 프로젝트 경로 추가
sys.path.append('../')
app = FastAPI(title="Trading Backtest API", version="1.0.0")
CORS 설정 - React 개발서버 허용
app.add_middleware
backtest_runner = BacktestRunner()
@app.post("/api/backtest", response_model=BacktestResult) async def run_backtest(config: BacktestConfig): """백테스트 실행 및 결과 반환""" try: result = backtest_runner.run_backtest(config) return result except Exception as e: raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/default-config") async def get_default_config(): """기본 설정값 반환 - config.py에서 읽어옴""" # zillion/src/config.py의 기본값들을 반환
@app.get("/api/available-tickers") async def get_tickers(): """data/ 폴더의 CSV 파일을 기준으로 사용 가능한 거래 종목 목록 반환""" # zillion/data/ 폴더 스캔해서 사용가능한 데이터 파일 목록 반환
if name == "main": import uvicorn uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)``` 

#### models/config_model.py (설정 데이터 모델)
```

python from pydantic import BaseModel, Field from typing import Optional from datetime import datetime
class BacktestConfig(BaseModel): # 기본 설정 ticker: str = Field(default="XRP/KRW", description="거래 종목") timeframe: str = Field(default="1h", description="시간봉") initial_capital: float = Field(default=3_000_000.0, description="초기 자본")
# 터틀 전략 설정  
turtle_entry_period: int = Field(default=20, description="진입 기준 기간")
turtle_atr_period: int = Field(default=20, description="ATR 계산 기간")
turtle_risk_rate: float = Field(default=1.0, description="리스크 비율 (%)")
turtle_max_units: int = Field(default=4, description="최대 피라미딩 유닛")
turtle_trailing_multiplier: float = Field(default=2.0, description="트레일링 승수")

# 백테스트 기간
start_date: Optional[str] = Field(default=None, description="시작일 (YYYY-MM-DD)")
end_date: Optional[str] = Field(default=None, description="종료일 (YYYY-MM-DD)")

# 출력 옵션
print_all_trades: bool = Field(default=False, description="전체 거래내역 출력")
print_monthly: bool = Field(default=True, description="월별 수익률 출력")
print_crash: bool = Field(default=False, description="폭락 구간 분석 출력")

class Config:
    schema_extra = {
        "example": {
            "ticker": "XRP/KRW",
            "timeframe": "1h",
            "initial_capital": 3000000.0,
            "turtle_entry_period": 20,
            "turtle_atr_period": 20,
            "turtle_risk_rate": 1.0,
            "turtle_max_units": 4,
            "turtle_trailing_multiplier": 2.0,
            "print_monthly": True
        }
    }``` 

#### backtest_runner.py (백테스트 실행 래퍼)
```

python import subprocess import json import tempfile import os import sys from datetime import datetime from models.config_model import BacktestConfig
class BacktestRunner: def init(self): self.zillion_path = os.path.abspath("../") # zillion 프로젝트 경로
def run_backtest(self, config: BacktestConfig) -> dict:
    """기존 백테스트 코드를 실행하고 결과를 파싱"""
    
    # 1. config.py 임시 백업 및 수정
    temp_config_path = self._update_config_file(config)
    
    try:
        # 2. 백테스트 실행
        result = subprocess.run([
            sys.executable, "-m", "test.backtest"
        ], 
        cwd=self.zillion_path,
        capture_output=True,
        text=True,
        timeout=300  # 5분 타임아웃
        )
        
        if result.returncode != 0:
            raise Exception(f"백테스트 실행 실패: {result.stderr}")
        
        # 3. 결과 파싱 및 구조화
        parsed_result = self._parse_backtest_output(result.stdout)
        
        # 4. 데이터베이스에서 거래내역 조회
        trades = self._get_trades_from_db()
        
        return {
            "success": True,
            "execution_time": parsed_result.get("execution_time", 0),
            "chart_data": parsed_result.get("chart_data", {}),
            "metrics": parsed_result.get("metrics", {}),
            "trades": trades,
            "logs": parsed_result.get("logs", [])
        }
        
    finally:
        # 5. 설정 파일 복원
        self._restore_config_file(temp_config_path)

def _update_config_file(self, config: BacktestConfig) -> str:
    """config.py 파일을 임시로 수정"""
    # 구현 필요: config.py 파일 읽어서 설정값들 업데이트
    pass

def _restore_config_file(self, backup_path: str):
    """config.py 파일 복원"""
    pass

def _parse_backtest_output(self, stdout: str) -> dict:
    """백테스트 출력을 파싱해서 구조화된 데이터로 변환"""
    # 구현 필요: stdout에서 차트 데이터, 성과지표 등을 추출
    pass

def _get_trades_from_db(self) -> list:
    """SQLite DB에서 거래내역 조회"""
    # 구현 필요: trading.db에서 거래내역 조회
    pass``` 

## 🎨 프론트엔드 상세 설계

### 메인 앱 구조 (App.jsx)
```

jsx import React, { useState, useEffect } from 'react'; import ConfigPanel from './components/ConfigPanel'; import ChartSection from './components/ChartSection'; import ResultsPanel from './components/ResultsPanel'; import { runBacktest, getDefaultConfig } from './services/api';
function App() { const [config, setConfig] = useState(null); const [results, setResults] = useState(null); const [loading, setLoading] = useState(false); const [error, setError] = useState(null);
useEffect(() => { // 초기 설정 로드 loadDefaultConfig(); }, []);
const loadDefaultConfig = async () => { try { const defaultConfig = await getDefaultConfig(); setConfig(defaultConfig); } catch (err) { setError('기본 설정 로드 실패'); } };
const handleRunBacktest = async (backtestConfig) => { setLoading(true); setError(null);
try {
  const result = await runBacktest(backtestConfig);
  setResults(result);
} catch (err) {
  setError(`백테스트 실행 실패: ${err.message}`);
} finally {
  setLoading(false);
}
};
return (
{/* 헤더 */} 🐢 터틀 트레이딩 백테스트 대시보드 zillion v1.0 {loading && ( )}
  <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
    {/* 에러 표시 */}
    {error && (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex">
          <div className="text-red-800">⚠️ {error}</div>
        </div>
      </div>
    )}

    {/* 설정 패널 */}
    {config && (
      <ConfigPanel 
        initialConfig={config}
        onRunBacktest={handleRunBacktest} 
        loading={loading} 
      />
    )}
    
    {/* 결과 영역 */}
    {results && (
      <>
        <ChartSection data={results.chart_data} />
        <ResultsPanel 
          metrics={results.metrics}
          trades={results.trades}
          logs={results.logs}
          executionTime={results.execution_time}
        />
      </>
    )}

    {/* 로딩 중일 때 스켈레톤 */}
    {loading && (
      <div className="space-y-6">
        <div className="bg-white rounded-lg shadow p-6">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/4 mb-4"></div>
            <div className="space-y-3">
              <div className="h-3 bg-gray-200 rounded"></div>
              <div className="h-3 bg-gray-200 rounded w-5/6"></div>
            </div>
          </div>
        </div>
      </div>
    )}
  </main>
</div>
); }
export default App;``` 

### 설정 패널 (ConfigPanel.jsx)
```

jsx import React, { useState } from 'react';
const ConfigPanel = ({ initialConfig, onRunBacktest, loading }) => { const [config, setConfig] = useState(initialConfig); const [collapsed, setCollapsed] = useState(false);
const updateConfig = (key, value) => { setConfig(prev => ({ ...prev, [key]: value })); };
const handleSubmit = (e) => { e.preventDefault(); onRunBacktest(config); };
return (
⚙️ 백테스트 설정
<button onClick={() => setCollapsed(!collapsed)} className="text-gray-400 hover:text-gray-600" > {collapsed ? '▼' : '▲'}
  {!collapsed && (
    <form onSubmit={handleSubmit} className="p-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* 기본 설정 */}
        <div>
          <h3 className="text-lg font-medium text-gray-900 mb-4">📊 기본 설정</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                거래 종목
              </label>
              <select 
                value={config.ticker}
                onChange={(e) => updateConfig('ticker', e.target.value)}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              >
                <option value="XRP/KRW">XRP/KRW</option>
                <option value="BTC/KRW">BTC/KRW</option>
                <option value="ETH/KRW">ETH/KRW</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                시간봉
              </label>
              <select 
                value={config.timeframe}
                onChange={(e) => updateConfig('timeframe', e.target.value)}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
              >
                <option value="1h">1시간</option>
                <option value="4h">4시간</option>
                <option value="1d">1일</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                초기 자본 (원)
              </label>
              <input
                type="number"
                value={config.initial_capital}
                onChange={(e) => updateConfig('initial_capital', Number(e.target.value))}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                min="100000"
                step="100000"
              />
            </div>
          </div>
        </div>

        {/* 터틀 전략 설정 */}
        <div>
          <h3 className="text-lg font-medium text-gray-900 mb-4">🐢 터틀 전략</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                진입 기간 (봉)
              </label>
              <input
                type="number"
                value={config.turtle_entry_period}
                onChange={(e) => updateConfig('turtle_entry_period', Number(e.target.value))}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                min="10"
                max="50"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                ATR 기간 (봉)
              </label>
              <input
                type="number"
                value={config.turtle_atr_period}
                onChange={(e) => updateConfig('turtle_atr_period', Number(e.target.value))}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                min="10"
                max="30"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                리스크 비율 (%)
              </label>
              <input
                type="number"
                step="0.1"
                value={config.turtle_risk_rate}
                onChange={(e) => updateConfig('turtle_risk_rate', Number(e.target.value))}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                min="0.1"
                max="5.0"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                최대 유닛 수
              </label>
              <input
                type="number"
                value={config.turtle_max_units}
                onChange={(e) => updateConfig('turtle_max_units', Number(e.target.value))}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                min="1"
                max="8"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                트레일링 승수
              </label>
              <input
                type="number"
                step="0.1"
                value={config.turtle_trailing_multiplier}
                onChange={(e) => updateConfig('turtle_trailing_multiplier', Number(e.target.value))}
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                min="0.5"
                max="5.0"
              />
            </div>
          </div>
        </div>

        {/* 실행 옵션 */}
        <div>
          <h3 className="text-lg font-medium text-gray-900 mb-4">🚀 실행 옵션</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                백테스트 기간
              </label>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="date"
                  value={config.start_date || ''}
                  onChange={(e) => updateConfig('start_date', e.target.value)}
                  className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                />
                <input
                  type="date"
                  value={config.end_date || ''}
                  onChange={(e) => updateConfig('end_date', e.target.value)}
                  className="rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">비어있으면 전체 기간</p>
            </div>
            
            <div className="space-y-3">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={config.print_monthly}
                  onChange={(e) => updateConfig('print_monthly', e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="ml-2 text-sm text-gray-700">월별 수익률 출력</span>
              </label>
              
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={config.print_all_trades}
                  onChange={(e) => updateConfig('print_all_trades', e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="ml-2 text-sm text-gray-700">모든 거래내역 출력</span>
              </label>
              
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={config.print_crash}
                  onChange={(e) => updateConfig('print_crash', e.target.checked)}
                  className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="ml-2 text-sm text-gray-700">폭락 구간 분석</span>
              </label>
            </div>
          </div>
          
          <button
            type="submit"
            disabled={loading}
            className="mt-6 w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-lg transition-colors duration-200 flex items-center justify-center"
          >
            {loading ? (
              <>
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="m4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                실행 중...
              </>
            ) : (
              '🚀 백테스트 실행'
            )}
          </button>
        </div>
      </div>
    </form>
  )}
</div>
); };
export default ConfigPanel;``` 

### 차트 섹션 (ChartSection.jsx)
```

jsx import React, { useState } from 'react'; import { Line, Bar } from 'react-chartjs-2'; import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, BarElement, Title, Tooltip, Legend, Filler } from 'chart.js';
ChartJS.register;
const ChartSection = ({ data }) => { const [activeChart, setActiveChart] = useState('equity');
// 공통 차트 옵션 const commonOptions = { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top', }, tooltip: { mode: 'index', intersect: false, } }, scales: { x: { display: true, title: { display: true, text: '날짜' } }, y: { display: true, title: { display: true, text: '값' } } }, interaction: { mode: 'nearest', axis: 'x', intersect: false } };
// 수익률 곡선 차트 설정 const equityChartData = { labels: data.dates, datasets: };
// 잔고 변화 차트 const balanceChartData = { labels: data.dates, datasets: };
// 월별 수익률 차트 const monthlyReturnsData = { labels: data.monthly_labels, datasets: };
// 드로우다운 차트 const drawdownChartData = { labels: data.dates, datasets: };
const charts = { equity: { title: '📈 누적 수익률', component: , description: '시간에 따른 누적 수익률 변화' }, balance: { title: '💰 자산 변화', component: , description: '총 자산(KRW + 보유 코인)의 변화' }, monthly: { title: '📊 월별 수익률', component: , description: '월별 수익률 분포' }, drawdown: { title: '📉 드로우다운', component: , description: '최고점 대비 하락률' } };
return (
📈 백테스트 차트
{charts[activeChart]?.description}
  {/* 차트 탭 */}
  <div className="px-6 py-3 border-b border-gray-200">
    <nav className="flex space-x-8">
      {Object.entries(charts).map(([key, chart]) => (
        <button
          key={key}
          onClick={()=> setActiveChart(key)}
          className={`py-2 px-1 border-b-2 font-medium text-sm transition-colors duration-200 ${
            activeChart === key
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          }`}
        >
          {chart.title}
        </button>
      ))}
    </nav>
  </div>

  {/* 차트 영역 */}
  <div className="p-6">
    <div className="h-96">
      {charts[activeChart]?.component}
    </div>
  </div>
</div>
); };
export default ChartSection;``` 

### 결과 패널 (ResultsPanel.jsx)
```

jsx import React, { useState } from 'react'; import MetricsDisplay from './MetricsDisplay'; import TradeTable from './TradeTable'; import LogViewer from './LogViewer';
const ResultsPanel = ({ metrics, trades, logs, executionTime }) => { const [activeTab, setActiveTab] = useState('metrics');
const tabs = ;
return (
{/* 탭 헤더 */}
📋 백테스트 결과
{tabs.map((tab) => (  setActiveTab(tab.id)} className={py-3 px-1 border-b-2 font-medium text-sm transition-colors duration-200 ${ activeTab === tab.id ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300' }} > {tab.name} {tab.count !== null &&   } ))} 
  {/* 탭 내용 */}
  <div className="p-6">
    {tabs.find(tab => tab.id === activeTab)?.component}
  </div>
</div>
); };
export default ResultsPanel;buttonlatex_unknown_tagbutton``` 

## 🚀 구현 단계별 가이드

### Phase 1: 기본 구조 설정 (1-2일)
1. **프로젝트 초기화**
   ```bash
   # 백엔드
   mkdir trading-dashboard
   cd trading-dashboard
   mkdir backend frontend
   
   # 프론트엔드 (Vite + React)
   cd frontend
   npm create vite@latest . -- --template react
   npm install
   npm install chart.js react-chartjs-2 @tailwindcss/forms
   npm install -D tailwindcss postcss autoprefixer
   npx tailwindcss init -p
   
   # 백엔드 (FastAPI)
   cd ../backend
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install fastapi uvicorn pydantic python-multipart
   ```

2. **기본 API 서버 설정**
   - FastAPI 기본 구조 생성
   - CORS 설정
   - 헬스체크 엔드포인트

3. **React 앱 기본 구조**
   - Tailwind CSS 설정
   - 기본 컴포넌트 생성
   - API 서비스 모듈

### Phase 2: 백테스트 연동 (2-3일)
1. **백테스트 실행 래퍼 구현**
   - subprocess를 통한 기존 백테스트 실행
   - config.py 동적 수정 기능
   - 결과 파싱 로직

2. **데이터베이스 연동**
   - SQLite 거래내역 조회
   - 결과 데이터 구조화

3. **API 엔드포인트 완성**
   - POST /api/backtest 구현
   - 에러 처리 및 검증
   - 타임아웃 설정

### Phase 3: UI 구현 (2-3일)
1. **설정 패널 구현**
   - 폼 입력 컴포넌트
   - 유효성 검사
   - 기본값 로드

2. **차트 구현**
   - Chart.js 설정
   - 수익률 곡선 차트
   - 월별 수익률 바차트
   - 드로우다운 차트

3. **결과 표시**
   - 성과지표 카드
   - 거래내역 테이블
   - 로그 뷰어

### Phase 4: 고도화 (1-2일)
1. **사용자 경험 개선**
   - 로딩 상태 관리
   - 에러 처리 UI
   - 스켈레톤 로딩

2. **추가 기능**
   - 결과 내보내기 (CSV, JSON)
   - 차트 확대/축소
   - 반응형 디자인

## 📦 필요한 패키지

### 백엔드 (requirements.txt)
```

fastapi==0.104.1 uvicorn[standard]==0.24.0 pydantic==2.5.0 python-multipart==0.0.6 pandas>=1.5.0 numpy>=1.24.0``` 

### 프론트엔드 (package.json)
```

json { "name": "trading-dashboard", "version": "1.0.0", "type": "module", "scripts": { "dev": "vite", "build": "vite build", "preview": "vite preview" }, "dependencies": { "react": "^18.2.0", "react-dom": "^18.2.0", "chart.js": "^4.4.0", "react-chartjs-2": "^5.2.0" }, "devDependencies": { "@types/react": "^18.2.37", "@types/react-dom": "^18.2.15", "@vitejs/plugin-react": "^4.0.3", "autoprefixer": "^10.4.16", "postcss": "^8.4.31", "tailwindcss": "^3.3.6", "@tailwindcss/forms": "^0.5.7", "vite": "^4.4.5" } }``` 

## 🎯 핵심 기능 요구사항

### ✅ 필수 기능 (MVP)
- [ ] 백테스트 설정 입력 폼
- [ ] 백테스트 실행 및 결과 표시
- [ ] 기본 차트 (수익률 곡선)
- [ ] 성과지표 표시
- [ ] 거래내역 테이블

### 🔄 선택적 기능
- [ ] 월별 수익률 바 차트
- [ ] 드로우다운 차트  
- [ ] 실행 로그 뷰어
- [ ] 결과 내보내기 (CSV)
- [ ] 다크모드 지원
- [ ] 차트 줌/팬 기능

### 🚀 고급 기능 (향후 확장)
- [ ] 다중 전략 비교
- [ ] 실시간 백테스트 진행률
- [ ] 설정 프리셋 저장/로드
- [ ] 결과 히스토리 관리

## 📋 개발시 주의사항

1. **기존 zillion 프로젝트와의 연동**
   - 상대 경로 주의 (../zillion)
   - config.py 파일 수정시 백업 필수
   - SQLite DB 파일 경로 확인

2. **데이터 파싱**
   - 백테스트 출력 형식 변경 가능성 대비
   - 숫자 포맷팅 (쉼표, 소수점 처리)
   - 날짜 형식 통일

3. **에러 처리**
   - 백테스트 실행 실패 시나리오
   - 네트워크 오류 처리
   - 잘못된 설정값 검증

4. **성능 최적화**
   - 큰 데이터셋 처리 시 메모리 사용량
   - 차트 렌더링 최적화
   - API 응답 시간 고려

## 📝 추가 고려사항

1. **보안**
   - API 키 등 민감정보 보호
   - CORS 설정 검토
   - 입력값 검증 강화

2. **확장성**
   - 새로운 전략 추가 용이성
   - 다른 거래소 지원 가능성
   - 멀티 심볼 백테스트

3. **사용성**
   - 직관적인 UI/UX
   - 도움말 및 툴팁 제공
   - 키보드 단축키 지원

---

**문서 작성일**: 2024-03-09  
**버전**: 1.0  
**작성자**: AI Assistant

이 문서는 Cursor 에이전트가 단계적으로 구현할 수 있도록 상세한 설계 정보를 제공합니다. 각 단계별로 구현 후 테스트를 거쳐 다음 단계로 진행하시기 바랍니다.
```

프로젝트 루트에 FPRD.md 파일을 생성했습니다!
이 문서는 Cursor 에이전트가 프론트엔드 시각화 도구를 구현할 수 있도록 다음 내용을 포함하고 있습니다:
📋 주요 내용
시스템 아키텍처 및 프로젝트 구조
상세한 API 설계 및 데이터 모델
React 컴포넌트별 구현 가이드
단계별 개발 로드맵
필요한 패키지 목록
🎯 핵심 기능
백테스트 설정 입력 폼
수익률/잔고/월별수익률 차트
성과지표 대시보드
거래내역 테이블
실행 로그 뷰어
이제 Cursor 에이전트에게 이 문서를 전달하시면, 단계별로 웹 기반 백테스트 시각화 도구를 구현할 수 있습니다! 🚀
