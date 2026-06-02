import React, { useState, useEffect } from 'react'
import axios from 'axios'

interface NewsArticle {
  title: string
  summary: string
  source: string
  sentiment_label: string
  sentiment_score: number
  relevance_score: number
  published_at: string
  entities: string[]
  url: string
}

interface SentimentSummary {
  overall_sentiment: string
  bullish_ratio: number
  bullish_count: number
  bearish_count: number
  neutral_count: number
  dominant_entities: string[]
}

const NewsPanel: React.FC = () => {
  const [news, setNews] = useState<NewsArticle[]>([])
  const [summary, setSummary] = useState<SentimentSummary | null>(null)
  const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

  useEffect(() => {
    const fetchNews = async () => {
      try {
        const [newsRes, summaryRes] = await Promise.all([
          axios.get(`${API_BASE}/api/news/enhanced`),
          axios.get(`${API_BASE}/api/news/sentiment-summary`),
        ])
        
        if (newsRes.data?.data) {
          setNews(newsRes.data.data)
        }
        if (summaryRes.data?.data) {
          setSummary(summaryRes.data.data)
        }
      } catch (error) {
        console.error('Error fetching news:', error)
      }
    }

    fetchNews()
    const interval = setInterval(fetchNews, 10000) // Update every 10 seconds
    return () => clearInterval(interval)
  }, [API_BASE])

  const getSentimentColor = (label: string): string => {
    switch (label) {
      case 'positive':
        return 'bg-green-900 border-l-4 border-green-500 text-green-50'
      case 'negative':
        return 'bg-red-900 border-l-4 border-red-500 text-red-50'
      default:
        return 'bg-slate-800 border-l-4 border-slate-600 text-slate-50'
    }
  }

  const getSentimentBadge = (label: string): string => {
    switch (label) {
      case 'positive':
        return '📈'
      case 'negative':
        return '📉'
      default:
        return '➡️'
    }
  }

  const getOverallSentimentColor = (sentiment: string): string => {
    switch (sentiment) {
      case 'bullish':
        return 'bg-green-600 text-green-50'
      case 'bearish':
        return 'bg-red-600 text-red-50'
      default:
        return 'bg-slate-600 text-slate-50'
    }
  }

  return (
    <div className="space-y-4">
      {/* Sentiment Summary */}
      {summary && (
        <div className={`${getOverallSentimentColor(summary.overall_sentiment)} rounded-lg p-4`}>
          <div className="text-center">
            <p className="text-sm font-semibold opacity-90">Market Sentiment</p>
            <p className="text-2xl font-bold uppercase">{summary.overall_sentiment}</p>
            <div className="flex justify-center gap-4 text-xs mt-2 font-medium">
              <span>🟢 {summary.bullish_count}</span>
              <span>🔴 {summary.bearish_count}</span>
              <span>⚪ {summary.neutral_count}</span>
            </div>
          </div>
          
          {summary.dominant_entities.length > 0 && (
            <div className="mt-3 pt-3 border-t border-current border-opacity-20">
              <p className="text-xs font-semibold mb-2">Key Entities:</p>
              <div className="flex flex-wrap gap-1">
                {summary.dominant_entities.map((entity) => (
                  <span key={entity} className="text-xs bg-current bg-opacity-20 px-2 py-1 rounded">
                    {entity}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* News Feed */}
      <div className="space-y-3">
        <h3 className="text-lg font-bold text-slate-100">Energy News & Analysis</h3>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {news.map((article, idx) => (
            <a
              key={idx}
              href={article.url || '#'}
              target="_blank"
              rel="noopener noreferrer"
              className={`${getSentimentColor(article.sentiment_label)} p-3 rounded cursor-pointer hover:opacity-80 transition-opacity block`}
            >
              <div className="flex items-start gap-2">
                <span className="text-lg flex-shrink-0">{getSentimentBadge(article.sentiment_label)}</span>
                <div className="flex-grow min-w-0">
                  <p className="font-semibold text-sm leading-tight">{article.title}</p>
                  <p className="text-xs opacity-70 mt-1 line-clamp-2">{article.summary}</p>
                  <div className="flex justify-between items-center mt-2 text-xs opacity-60">
                    <span>{article.source}</span>
                    <span>Score: {(article.relevance_score * 100).toFixed(0)}%</span>
                  </div>
                  {article.entities && article.entities.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {article.entities.map((entity) => (
                        <span
                          key={entity}
                          className="text-xs bg-current bg-opacity-20 px-1.5 py-0.5 rounded"
                        >
                          {entity}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}

export default NewsPanel
