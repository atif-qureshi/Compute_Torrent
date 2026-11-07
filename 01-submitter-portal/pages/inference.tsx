import React, { useCallback, useEffect, useState } from 'react'
import Head from 'next/head'
import { useRouter } from 'next/router'
import AppLayout from '../components/AppLayout'
import StatusBadge from '../components/StatusBadge'
import StatCard from '../components/StatCard'
import DiagnosticBanner from '../components/DiagnosticBanner'
import LayerPipelineVisualizer from '../components/LayerPipelineVisualizer'

interface ModelSpec {
  id: string
  label: string
  layers: number
  hiddenSize: number
  description: string
  tag: string
}

const SUPPORTED_MODELS: ModelSpec[] = [
  {
    id: 'TinyLlama/TinyLlama-1.1B-Chat-v1.0',
    label: 'TinyLlama 1.1B Chat',
    layers: 22,
    hiddenSize: 2048,
    description: '1.1 Billion parameter instruction model. Slices across 2+ PCs with 2-3 GB RAM each.',
    tag: 'Recommended · 22 Layers',
  },
  {
    id: 'bigscience/bloomz-560m',
    label: 'BLOOMZ 560M Instruction',
    layers: 24,
    hiddenSize: 1024,
    description: 'Multilingual instruction-following model. Highly lightweight per-layer footprint.',
    tag: 'Lightweight · 24 Layers',
  },
  {
    id: 'bigscience/bloom-560m',
    label: 'BLOOM 560M Base',
    layers: 24,
    hiddenSize: 1024,
    description: 'Base foundation autoregressive language model.',
    tag: 'Base · 24 Layers',
  },
]

const PROMPT_SUGGESTIONS = [
  'Explain volunteer distributed computing in one concise sentence.',
  'Write a Python function to perform binary search on a sorted list.',
  'What are the advantages of decentralized peer-to-peer AI inference?',
]

async function api(path: string, options?: RequestInit) {
  const response = await fetch(`/api/ct/distributed${path}`, options)
  const body = await response.json()
  if (!response.ok) {
    const detail = body.detail || body.message
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`)
  }
  return body
}

const ACTIVE_STAGES = [
  'queued',
  'resolving',
  'profiling_capacity',
  'loading',
  'downloading_model',
  'loading_reference',
  'connecting_layers',
  'running',
  'verifying',
  'benchmarking',
]

const stageLabel = (status?: string) =>
  ({
    queued: 'Queued in orchestrator',
    resolving: 'Resolving model configuration',
    profiling_capacity: 'Measuring provider capacity & RAM',
    assigning: 'Assigning contiguous layer partitions',
    sent: 'Starting provider runtime containers',
    loading: 'Streaming transformer layer weights',
    serving: 'Serving layers on DHT network',
    downloading_model: 'Downloading tokenizer & model metadata',
    connecting_layers: 'Connecting distributed pipeline layers',
    loading_reference: 'Downloading model weights',
    running: 'Generating tokens across peer nodes',
    verifying: 'Verifying layer activations',
    benchmarking: 'Benchmarking latency',
    completed: 'Completed successfully',
    failed: 'Execution failed',
    cancelled: 'Cancelled by operator',
  }[status || ''] || status || 'Waiting')

export default function Inference() {
  const router = useRouter()

  // Deployment Form State
  const [mode, setMode] = useState<'guided' | 'raw'>('guided')
  const [selectedModelId, setSelectedModelId] = useState<string>('TinyLlama/TinyLlama-1.1B-Chat-v1.0')
  const [prompt, setPrompt] = useState<string>('Explain volunteer computing in one sentence.')
  const [maxNewTokens, setMaxNewTokens] = useState<number>(32)
  const [minPeers, setMinPeers] = useState<number>(2)

  // Raw Recipe State
  const [rawContent, setRawContent] = useState<string>('')
  const [rawFormat, setRawFormat] = useState<'json' | 'xml'>('json')

  // Real-time Platform State
  const [jobs, setJobs] = useState<any[]>([])
  const [network, setNetwork] = useState<any>({ providers: [], status: 'checking' })
  const [selectedJobId, setSelectedJobId] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [submitting, setSubmitting] = useState<boolean>(false)
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false)
  const [copiedResult, setCopiedResult] = useState<boolean>(false)

  // URL query parameter pre-selection
  useEffect(() => {
    if (router.query.model === 'bloomz') {
      setSelectedModelId('bigscience/bloomz-560m')
    } else if (router.query.model === 'bloom') {
      setSelectedModelId('bigscience/bloom-560m')
    } else if (router.query.model === 'tinyllama') {
      setSelectedModelId('TinyLlama/TinyLlama-1.1B-Chat-v1.0')
    }
  }, [router.query.model])

  const refresh = useCallback(async () => {
    setIsRefreshing(true)
    try {
      const [state, history] = await Promise.all([api('/status'), api('/jobs')])
      setNetwork(state || { providers: [], status: 'checking' })
      setJobs(history || [])
    } catch (e: any) {
      setError(e.message || 'Coordinator unavailable')
    } finally {
      setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 4000)
    return () => clearInterval(timer)
  }, [refresh])

  const providers = network.providers || []
  const readyProviders = providers.filter((p: any) => p.layer_ready)
  const isDhtReady = network.status === 'ready'
  const isJobRunning = jobs.some((j) => ACTIVE_STAGES.includes(j.status))

  const currentJob = jobs.find((j) => j.id === selectedJobId) || jobs[0]

  // Submit Handler
  const handleDeploy = async () => {
    setError('')
    setSubmitting(true)

    let payloadContent: string = ''
    let payloadFormat: 'json' | 'xml' = 'json'

    if (mode === 'guided') {
      const spec = {
        model_id: selectedModelId,
        revision: 'main',
        prompt: prompt.trim(),
        max_new_tokens: Number(maxNewTokens) || 32,
        min_peers: Number(minPeers) || 2,
        max_peers: 8,
        benchmark: false,
      }
      payloadContent = JSON.stringify(spec, null, 2)
      payloadFormat = 'json'
    } else {
      if (!rawContent) {
        setError('Please enter or upload a valid JSON or XML recipe.')
        setSubmitting(false)
        return
      }
      if (rawFormat === 'json') {
        try {
          JSON.parse(rawContent)
        } catch {
          setError('Raw recipe content is not valid JSON.')
          setSubmitting(false)
          return
        }
      }
      payloadContent = rawContent
      payloadFormat = rawFormat
    }

    try {
      const newJob = await api('/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: payloadContent, format: payloadFormat }),
      })
      if (newJob?.id) {
        setSelectedJobId(newJob.id)
      }
      await refresh()
    } catch (e: any) {
      setError(e.message || 'Deployment submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  // Upload handler for raw mode
  const handleFileUpload = async (file?: File) => {
    if (!file) return
    if (file.size > 65536) {
      setError('Recipe file must be smaller than 64 KiB.')
      return
    }
    const isJson = /\.json$/i.test(file.name)
    const isXml = /\.xml$/i.test(file.name)
    if (!isJson && !isXml) {
      setError('File must be a .json or .xml document.')
      return
    }

    try {
      const text = await file.text()
      if (isXml) {
        const parsed = new DOMParser().parseFromString(text, 'text/xml')
        if (parsed.getElementsByTagName('parsererror').length || parsed.documentElement.tagName !== 'inference') {
          throw new Error('XML root tag must be <inference> without attributes.')
        }
        setRawContent(text)
        setRawFormat('xml')
      } else {
        const parsed = JSON.parse(text)
        if (!parsed.model_id) throw new Error('Recipe JSON must contain model_id')
        setRawContent(text)
        setRawFormat('json')
      }
      setError('')
    } catch (err: any) {
      setError(err.message || 'File parsing failed')
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedResult(true)
    setTimeout(() => setCopiedResult(false), 2000)
  }

  const selectedModelSpec = SUPPORTED_MODELS.find((m) => m.id === selectedModelId) || SUPPORTED_MODELS[0]

  return (
    <AppLayout
      title="Model Studio"
      subtitle="Partition and deploy transformer layers dynamically across volunteer computers."
      actions={
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={refresh}
            style={{
              padding: '6px 12px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              fontSize: '12px',
              color: '#cbd5e1',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>{isRefreshing ? '🔄' : '↻'}</span>
            <span>{isRefreshing ? 'Refreshing…' : 'Refresh Telemetry'}</span>
          </button>
          <a
            href="/deployments"
            style={{
              padding: '6px 12px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              fontSize: '12px',
              color: '#60a5fa',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>📜</span>
            <span>Runs History ({jobs.length})</span>
          </a>
        </div>
      }
    >
      {/* Actionable Error Banner if any */}
      {error && (
        <DiagnosticBanner
          error={error}
          onDismiss={() => setError('')}
          onRetry={refresh}
        />
      )}

      {/* Pre-Flight Health Strip */}
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
          marginBottom: '24px',
        }}
      >
        <StatCard
          label="Ready Layer Providers"
          value={
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
              <span>{readyProviders.length}</span>
              <span style={{ fontSize: '14px', color: '#64748b', fontWeight: 500 }}>
                / {providers.length} Connected
              </span>
            </div>
          }
          subtext={
            readyProviders.length >= 2
              ? '✅ Sufficient peers for multi-host layer allocation'
              : '⚠️ Connect at least 2 layer-ready PCs to deploy'
          }
          icon="🖥️"
          statusColor={readyProviders.length >= 2 ? 'emerald' : 'amber'}
        />

        <StatCard
          label="Petals DHT Gateway"
          value={
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ textTransform: 'uppercase' }}>{isDhtReady ? 'Active' : network.status}</span>
              <StatusBadge status={isDhtReady ? 'ready' : 'checking'} size="sm" showDot={true} />
            </div>
          }
          subtext="Coordinator port 31331 open for peer DHT mesh"
          icon="🌐"
          statusColor={isDhtReady ? 'emerald' : 'amber'}
        />

        <StatCard
          label="Target Architecture"
          value={selectedModelSpec.label.split(' ')[0]}
          subtext={`${selectedModelSpec.layers} Layers · Partitioned dynamically`}
          icon="🧠"
          statusColor="blue"
        />

        <StatCard
          label="Deployment Status"
          value={isJobRunning ? 'Active Job Running' : 'Idle / Available'}
          subtext={isJobRunning ? 'P2P pipeline currently active' : 'Coordinator ready for new deployment'}
          icon="⚡"
          statusColor={isJobRunning ? 'amber' : 'emerald'}
        />
      </section>

      {/* Main Studio 2-Column Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '24px', marginBottom: '32px' }}>
        {/* Left Column: Model Configuration & Deployment Wizard */}
        <section
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '10px',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            gap: '20px',
          }}
        >
          {/* Section Header with Mode Toggle */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                STEP 01
              </span>
              <h2 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', margin: '2px 0 0' }}>
                Configure Model Deployment
              </h2>
            </div>

            {/* Mode Segmented Switch */}
            <div
              style={{
                display: 'inline-flex',
                backgroundColor: '#090d16',
                padding: '3px',
                borderRadius: '8px',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <button
                type="button"
                onClick={() => setMode('guided')}
                style={{
                  padding: '4px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: mode === 'guided' ? 600 : 500,
                  backgroundColor: mode === 'guided' ? '#3b82f6' : 'transparent',
                  color: mode === 'guided' ? '#ffffff' : '#94a3b8',
                }}
              >
                Guided Mode
              </button>
              <button
                type="button"
                onClick={() => setMode('raw')}
                style={{
                  padding: '4px 12px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: mode === 'raw' ? 600 : 500,
                  backgroundColor: mode === 'raw' ? '#3b82f6' : 'transparent',
                  color: mode === 'raw' ? '#ffffff' : '#94a3b8',
                }}
              >
                Raw Recipe (JSON/XML)
              </button>
            </div>
          </div>

          {mode === 'guided' ? (
            /* GUIDED WORKFLOW */
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {/* Step 1: Model Selection Cards */}
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, color: '#cbd5e1', display: 'block', marginBottom: '8px' }}>
                  Select Model Architecture
                </label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {SUPPORTED_MODELS.map((m) => {
                    const isSelected = selectedModelId === m.id
                    return (
                      <div
                        key={m.id}
                        onClick={() => setSelectedModelId(m.id)}
                        style={{
                          padding: '12px 14px',
                          borderRadius: '8px',
                          border: isSelected ? '1px solid #3b82f6' : '1px solid rgba(255, 255, 255, 0.08)',
                          backgroundColor: isSelected ? 'rgba(59, 130, 246, 0.08)' : '#090d16',
                          cursor: 'pointer',
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontWeight: 600, color: isSelected ? '#ffffff' : '#f8fafc', fontSize: '13px' }}>
                              {m.label}
                            </span>
                            <span
                              style={{
                                padding: '2px 6px',
                                borderRadius: '4px',
                                fontSize: '10px',
                                fontWeight: 600,
                                backgroundColor: isSelected ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255, 255, 255, 0.06)',
                                color: isSelected ? '#93c5fd' : '#94a3b8',
                              }}
                            >
                              {m.tag}
                            </span>
                          </div>
                          <p style={{ fontSize: '11px', color: '#94a3b8', margin: '4px 0 0' }}>
                            {m.description}
                          </p>
                        </div>
                        <input
                          type="radio"
                          name="model_selection"
                          checked={isSelected}
                          onChange={() => setSelectedModelId(m.id)}
                          style={{ accentColor: '#3b82f6', width: '16px', height: '16px', cursor: 'pointer' }}
                        />
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Step 2: Prompt Input */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <label htmlFor="promptInput" style={{ fontSize: '12px', fontWeight: 600, color: '#cbd5e1' }}>
                    Inference Prompt
                  </label>
                  <span style={{ fontSize: '11px', color: '#64748b' }}>
                    {prompt.length} characters
                  </span>
                </div>
                <textarea
                  id="promptInput"
                  rows={3}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Enter a prompt for the distributed language model…"
                  style={{
                    width: '100%',
                    backgroundColor: '#090d16',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    fontSize: '13px',
                    color: '#f8fafc',
                    resize: 'vertical',
                  }}
                />

                {/* Quick prompt suggestions */}
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
                  <span style={{ fontSize: '11px', color: '#64748b', alignSelf: 'center' }}>Examples:</span>
                  {PROMPT_SUGGESTIONS.map((s, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setPrompt(s)}
                      style={{
                        padding: '3px 8px',
                        backgroundColor: 'rgba(255, 255, 255, 0.04)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        borderRadius: '4px',
                        fontSize: '11px',
                        color: '#94a3b8',
                        cursor: 'pointer',
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = '#ffffff' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = '#94a3b8' }}
                    >
                      {s.length > 40 ? s.slice(0, 38) + '…' : s}
                    </button>
                  ))}
                </div>
              </div>

              {/* Step 3: Hyperparameters Row */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <label htmlFor="maxTokens" style={{ fontSize: '12px', fontWeight: 600, color: '#cbd5e1', display: 'block', marginBottom: '6px' }}>
                    Max New Tokens: <span style={{ color: '#60a5fa' }}>{maxNewTokens}</span>
                  </label>
                  <input
                    id="maxTokens"
                    type="range"
                    min={16}
                    max={128}
                    step={8}
                    value={maxNewTokens}
                    onChange={(e) => setMaxNewTokens(Number(e.target.value))}
                    style={{ width: '100%', accentColor: '#3b82f6' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#64748b' }}>
                    <span>16 tokens</span>
                    <span>128 tokens</span>
                  </div>
                </div>

                <div>
                  <label htmlFor="minPeers" style={{ fontSize: '12px', fontWeight: 600, color: '#cbd5e1', display: 'block', marginBottom: '6px' }}>
                    Minimum Slicing Peers: <span style={{ color: '#60a5fa' }}>{minPeers}</span>
                  </label>
                  <input
                    id="minPeers"
                    type="number"
                    min={2}
                    max={8}
                    value={minPeers}
                    onChange={(e) => setMinPeers(Number(e.target.value))}
                    style={{ width: '100%', backgroundColor: '#090d16' }}
                  />
                  <small style={{ fontSize: '10px', color: '#64748b' }}>
                    Layers will be partitioned across at least {minPeers} distinct PCs
                  </small>
                </div>
              </div>
            </div>
          ) : (
            /* RAW RECIPE WORKFLOW */
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <label
                style={{
                  border: '1px dashed rgba(255, 255, 255, 0.15)',
                  backgroundColor: '#090d16',
                  borderRadius: '8px',
                  padding: '24px',
                  textAlign: 'center',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <span style={{ fontSize: '24px' }}>📁</span>
                <span style={{ fontSize: '13px', fontWeight: 500, color: '#f8fafc' }}>
                  {rawContent ? 'Click to replace recipe file' : 'Drop or browse .JSON / .XML recipe file'}
                </span>
                <span style={{ fontSize: '11px', color: '#64748b' }}>
                  Supports custom model recipe specifications up to 64 KiB
                </span>
                <input
                  type="file"
                  accept=".json,.xml,application/json,text/xml,application/xml"
                  style={{ display: 'none' }}
                  onChange={(e) => handleFileUpload(e.target.files?.[0])}
                />
              </label>

              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => {
                    const sample = {
                      model_id: 'TinyLlama/TinyLlama-1.1B-Chat-v1.0',
                      revision: 'main',
                      prompt: 'Explain volunteer computing in one sentence.',
                      max_new_tokens: 32,
                      min_peers: 2,
                      max_peers: 4,
                      benchmark: false,
                    }
                    setRawContent(JSON.stringify(sample, null, 2))
                    setRawFormat('json')
                  }}
                  style={{
                    padding: '6px 12px',
                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '6px',
                    fontSize: '11px',
                    color: '#cbd5e1',
                  }}
                >
                  📋 Load Sample TinyLlama JSON
                </button>
                {rawContent && (
                  <button
                    type="button"
                    onClick={() => setRawContent('')}
                    style={{
                      padding: '6px 12px',
                      backgroundColor: 'rgba(244, 63, 94, 0.1)',
                      border: '1px solid rgba(244, 63, 94, 0.2)',
                      borderRadius: '6px',
                      fontSize: '11px',
                      color: '#fb7185',
                    }}
                  >
                    Clear Content
                  </button>
                )}
              </div>

              {rawContent && (
                <textarea
                  rows={8}
                  value={rawContent}
                  onChange={(e) => setRawContent(e.target.value)}
                  spellCheck={false}
                  style={{
                    width: '100%',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '12px',
                    backgroundColor: '#090d16',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '8px',
                    padding: '10px 12px',
                    color: '#60a5fa',
                  }}
                />
              )}
            </div>
          )}

          {/* Primary Submit Button */}
          <button
            onClick={handleDeploy}
            disabled={
              submitting ||
              isJobRunning ||
              readyProviders.length < 2 ||
              !isDhtReady ||
              (mode === 'raw' && !rawContent) ||
              (mode === 'guided' && !prompt.trim())
            }
            style={{
              padding: '12px 20px',
              backgroundColor: readyProviders.length >= 2 && isDhtReady && !isJobRunning ? '#3b82f6' : '#1e293b',
              color: readyProviders.length >= 2 && isDhtReady && !isJobRunning ? '#ffffff' : '#64748b',
              borderRadius: '8px',
              fontSize: '14px',
              fontWeight: 600,
              cursor: readyProviders.length >= 2 && isDhtReady && !isJobRunning ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              transition: 'background-color 0.15s ease',
            }}
          >
            {submitting ? (
              <span>⏳ Allocating Contiguous Layers & Submitting…</span>
            ) : isJobRunning ? (
              <span>⚡ A Model Inference Job is Currently Running</span>
            ) : !isDhtReady ? (
              <span>⚠️ Petals DHT Gateway Initializing</span>
            ) : readyProviders.length < 2 ? (
              <span>⚠️ Minimum 2 Layer-Ready Providers Required ({readyProviders.length} connected)</span>
            ) : (
              <span>🚀 Deploy Model & Run Distributed Pipeline →</span>
            )}
          </button>
        </section>

        {/* Right Column: Connected Provider Layer Readiness List */}
        <section
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '10px',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <span style={{ fontSize: '11px', fontWeight: 700, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  STEP 02
                </span>
                <h2 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', margin: '2px 0 0' }}>
                  Connected Layer Peers
                </h2>
              </div>
              <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                {readyProviders.length} of {providers.length} Ready
              </span>
            </div>

            {providers.length === 0 ? (
              <div
                style={{
                  padding: '30px',
                  textAlign: 'center',
                  backgroundColor: '#090d16',
                  borderRadius: '8px',
                  border: '1px dashed rgba(255, 255, 255, 0.1)',
                }}
              >
                <div style={{ fontSize: '24px', marginBottom: '8px' }}>💻</div>
                <div style={{ fontSize: '13px', fontWeight: 500, color: '#f8fafc' }}>
                  No provider PCs connected
                </div>
                <p style={{ fontSize: '11px', color: '#64748b', margin: '4px 0 12px' }}>
                  Run the provider desktop client on client machines and tick "Share model layers".
                </p>
                <a
                  href="/nodes"
                  style={{
                    fontSize: '11px',
                    color: '#60a5fa',
                    padding: '4px 10px',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderRadius: '4px',
                  }}
                >
                  View Setup Instructions →
                </a>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {providers.map((p: any) => {
                  const isReady = p.layer_ready
                  const prof = p.profile || {}
                  return (
                    <div
                      key={p.node_id}
                      style={{
                        backgroundColor: '#090d16',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        borderRadius: '8px',
                        padding: '12px 14px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                        <div>
                          <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '12px' }}>
                            {prof.cpu_model || `Node ${p.node_id.slice(-10)}`}
                          </div>
                          <div style={{ fontSize: '11px', color: '#64748b', fontFamily: 'var(--font-mono)' }}>
                            ID: {p.node_id.slice(-12)}
                          </div>
                        </div>
                        <StatusBadge status={p.state || 'idle'} size="sm" />
                      </div>

                      {/* Hardware Telemetry Bar */}
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(3, 1fr)',
                          gap: '6px',
                          padding: '6px 8px',
                          backgroundColor: 'rgba(255, 255, 255, 0.02)',
                          borderRadius: '6px',
                          fontSize: '11px',
                          marginBottom: '8px',
                        }}
                      >
                        <div>
                          <span style={{ color: '#64748b', display: 'block' }}>Free RAM</span>
                          <span style={{ color: '#cbd5e1', fontWeight: 600 }}>{prof.free_ram_gb ?? '—'} GB</span>
                        </div>
                        <div>
                          <span style={{ color: '#64748b', display: 'block' }}>VRAM</span>
                          <span style={{ color: '#cbd5e1', fontWeight: 600 }}>
                            {prof.VRAM ? `${(prof.VRAM / 1024).toFixed(1)} GB` : 'CPU'}
                          </span>
                        </div>
                        <div>
                          <span style={{ color: '#64748b', display: 'block' }}>Docker</span>
                          <span style={{ color: p.runtime_installed ? '#34d399' : '#fbbf24', fontWeight: 600 }}>
                            {p.runtime_installed ? 'Installed' : 'Pending'}
                          </span>
                        </div>
                      </div>

                      {/* Layer Readiness Reason */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px' }}>
                        <span style={{ color: isReady ? '#34d399' : '#fbbf24' }}>
                          {isReady ? '🟢 Ready for Layer Serving' : `⚠️ ${p.layer_reason || 'Unready'}`}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
            <a
              href="/nodes"
              style={{
                fontSize: '12px',
                color: '#60a5fa',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span>Manage Node Credentials & Join Tokens</span>
              <span>→</span>
            </a>
          </div>
        </section>
      </div>

      {/* SECTION 03: Distributed Model Execution Pipeline & Output */}
      <section
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '10px',
          padding: '24px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <span style={{ fontSize: '11px', fontWeight: 700, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              STEP 03
            </span>
            <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#f8fafc', margin: '2px 0 0' }}>
              Model Execution Pipeline & Outputs
            </h2>
          </div>
          <button
            onClick={refresh}
            style={{
              padding: '6px 12px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              fontSize: '12px',
              color: '#cbd5e1',
            }}
          >
            ↻ Refresh Pipeline
          </button>
        </div>

        {jobs.length === 0 ? (
          <div
            style={{
              padding: '40px',
              textAlign: 'center',
              backgroundColor: '#090d16',
              borderRadius: '8px',
              border: '1px dashed rgba(255, 255, 255, 0.1)',
              color: '#64748b',
              fontSize: '13px',
            }}
          >
            Your first distributed model run will appear here with live layer allocation schemes and verification proofs.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '24px' }}>
            {/* Left: Job History Picker */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderRight: '1px solid rgba(255, 255, 255, 0.08)', paddingRight: '16px' }}>
              <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Recent Runs ({jobs.length})
              </span>
              {jobs.map((j) => {
                const isSelected = currentJob?.id === j.id
                return (
                  <button
                    key={j.id}
                    onClick={() => setSelectedJobId(j.id)}
                    style={{
                      textAlign: 'left',
                      padding: '10px 12px',
                      borderRadius: '6px',
                      border: isSelected ? '1px solid #3b82f6' : '1px solid rgba(255, 255, 255, 0.06)',
                      backgroundColor: isSelected ? 'rgba(59, 130, 246, 0.1)' : '#090d16',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, color: '#f8fafc', fontSize: '12px' }}>
                        {j.spec?.model_id?.split('/').pop() || 'Model Job'}
                      </span>
                      <StatusBadge status={j.status} size="sm" />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
                      <span>{new Date(j.created_at * 1000).toLocaleTimeString()}</span>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{j.id.slice(0, 8)}…</span>
                    </div>
                  </button>
                )
              })}
            </div>

            {/* Right: Active / Selected Job Details */}
            {currentJob && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                      {currentJob.spec?.model_id}
                    </h3>
                    <div style={{ fontSize: '11px', color: '#64748b', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
                      Job ID: {currentJob.id}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <StatusBadge status={currentJob.status} />
                    {ACTIVE_STAGES.includes(currentJob.status) && (
                      <button
                        onClick={async () => {
                          try {
                            await api(`/jobs/${currentJob.id}`, { method: 'DELETE' })
                            await refresh()
                          } catch (e: any) {
                            setError(e.message)
                          }
                        }}
                        style={{
                          padding: '4px 10px',
                          backgroundColor: 'rgba(244, 63, 94, 0.1)',
                          border: '1px solid rgba(244, 63, 94, 0.25)',
                          borderRadius: '6px',
                          color: '#fb7185',
                          fontSize: '11px',
                          fontWeight: 500,
                        }}
                      >
                        🛑 Cancel Run
                      </button>
                    )}
                  </div>
                </div>

                {/* Milestone Progress Indicator if active */}
                {ACTIVE_STAGES.includes(currentJob.status) && (
                  <div
                    style={{
                      padding: '12px 16px',
                      backgroundColor: 'rgba(59, 130, 246, 0.08)',
                      border: '1px solid rgba(59, 130, 246, 0.2)',
                      borderRadius: '8px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                    }}
                  >
                    <div style={{ fontSize: '16px' }}>⚡</div>
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 600, color: '#60a5fa' }}>
                        Current Milestone: {stageLabel(currentJob.status)}
                      </div>
                      <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                        {currentJob.progress > 0 ? `Stage progress: ${currentJob.progress}% · ` : ''}
                        Providers streaming model weights to local memory
                      </div>
                    </div>
                  </div>
                )}

                {/* Layer Partitioning Visualizer */}
                <div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
                    Distributed Layer Partitioning Scheme
                  </div>
                  <LayerPipelineVisualizer
                    totalLayers={currentJob.spec?.layers || 22}
                    plan={currentJob.plan || []}
                    stageStatus={currentJob.stage_status || {}}
                    jobStatus={currentJob.status}
                  />
                </div>

                {/* Actionable Error Banner if Job Failed */}
                {currentJob.error && (
                  <DiagnosticBanner
                    error={currentJob.error}
                    onRetry={handleDeploy}
                  />
                )}

                {/* Verified Output Box */}
                {currentJob.result && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                        {currentJob.status === 'completed' ? '✅ Verified Generation Result' : 'Model Output'}
                      </span>
                      <button
                        onClick={() => copyToClipboard(currentJob.result)}
                        style={{
                          padding: '4px 10px',
                          backgroundColor: 'rgba(255, 255, 255, 0.06)',
                          border: '1px solid rgba(255, 255, 255, 0.1)',
                          borderRadius: '4px',
                          fontSize: '11px',
                          color: '#f8fafc',
                        }}
                      >
                        {copiedResult ? '✅ Copied' : '📄 Copy Result'}
                      </button>
                    </div>

                    <pre
                      style={{
                        padding: '16px',
                        backgroundColor: '#090d16',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '8px',
                        fontSize: '13px',
                        color: '#f8fafc',
                        whiteSpace: 'pre-wrap',
                        lineHeight: 1.6,
                      }}
                    >
                      {currentJob.result}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>
    </AppLayout>
  )
}
