'use client'

import { useEffect, useState } from 'react'
import { AppShell } from '@/components/app-shell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Check, AlertCircle, HardDrive } from 'lucide-react'
import type { Settings } from '@/lib/types'
import { getSettings, saveSettings } from '@/lib/api'

type SaveState = 'idle' | 'saving' | 'saved' | 'error'
type LoadState = 'loading' | 'ready' | 'error'

const IMAGE_MODEL_OPTIONS = [
  { value: 'stabilityai/stable-diffusion-xl-base-1.0', label: 'SDXL Base 1.0' },
  { value: 'segmind/SSD-1B', label: 'Segmind SSD-1B' },
  { value: 'stabilityai/sd-turbo', label: 'SD Turbo' },
  { value: 'Lykon/dreamshaper-xl-1-0', label: 'DreamShaper XL' },
  { value: 'SG161222/RealVisXL_V4.0', label: 'RealVisXL V4.0' },
]

const emptySettings: Settings = {
  ollamaUrl: '',
  modelName: '',
  timeout: 45,
  imageMode: 'balanced',
  imageWidth: 512,
  imageHeight: 768,
  imageSteps: 6,
  imageGuidance: 8.5,
  imageModel: '',
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(emptySettings)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [errors, setErrors] = useState<Partial<Record<keyof Settings, string>>>({})
  const [serverError, setServerError] = useState<string | null>(null)
  const [useCustomModelInput, setUseCustomModelInput] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        setLoadState('loading')
        setServerError(null)
        const loaded = await getSettings()
        if (cancelled) return
        setSettings(loaded)
        setUseCustomModelInput(!IMAGE_MODEL_OPTIONS.some((option) => option.value === loaded.imageModel))
        setLoadState('ready')
      } catch (error) {
        if (cancelled) return
        setLoadState('error')
        setServerError(error instanceof Error ? error.message : 'Failed to load settings')
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  const validateSettings = (): boolean => {
    const newErrors: Partial<Record<keyof Settings, string>> = {}

    if (!settings.ollamaUrl.trim()) {
      newErrors.ollamaUrl = 'Ollama URL is required'
    } else {
      try {
        new URL(settings.ollamaUrl)
      } catch {
        newErrors.ollamaUrl = 'Invalid URL format'
      }
    }

    if (!settings.modelName.trim()) {
      newErrors.modelName = 'Model name is required'
    }

    if (settings.timeout < 10 || settings.timeout > 600) {
      newErrors.timeout = 'Timeout must be between 10 and 600 seconds'
    }

    if (settings.imageWidth < 256 || settings.imageWidth > 2048) {
      newErrors.imageWidth = 'Width must be between 256 and 2048'
    }

    if (settings.imageHeight < 256 || settings.imageHeight > 2048) {
      newErrors.imageHeight = 'Height must be between 256 and 2048'
    }

    if (settings.imageSteps < 1 || settings.imageSteps > 100) {
      newErrors.imageSteps = 'Steps must be between 1 and 100'
    }

    if (settings.imageGuidance < 1 || settings.imageGuidance > 20) {
      newErrors.imageGuidance = 'Guidance must be between 1 and 20'
    }

    if (settings.imageMode === 'custom' && !settings.imageModel.trim()) {
      newErrors.imageModel = 'Image model is required'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSave = async () => {
    if (!validateSettings()) return

    try {
      setSaveState('saving')
      setServerError(null)
      const saved = await saveSettings(settings)
      setSettings(saved)
      setSaveState('saved')

      setTimeout(() => {
        setSaveState('idle')
      }, 2000)
    } catch (error) {
      setSaveState('error')
      setServerError(error instanceof Error ? error.message : 'Failed to save settings')
    }
  }

  const updateSetting = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
    if (errors[key]) {
      setErrors((prev) => ({ ...prev, [key]: undefined }))
    }
  }

  return (
    <AppShell>
      <div className="p-6 max-w-3xl">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-foreground">Settings</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Configure your local-first processing environment
          </p>
        </div>

        {serverError && (
          <div className="mb-6 rounded-xl border border-status-failed/30 bg-status-failed/10 p-4 text-sm text-status-failed">
            {serverError}
          </div>
        )}

        {/* Local-first Notice */}
        <div className="rounded-xl border border-border bg-card p-4 mb-6 flex items-start gap-3">
          <HardDrive className="h-5 w-5 text-muted-foreground mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-foreground">Local-first processing</p>
            <p className="text-sm text-muted-foreground mt-0.5">
              All processing happens on your machine. Configure your local Ollama server
              and image generation model below.
            </p>
          </div>
        </div>

        <div className="space-y-6">
          {/* Ollama Configuration */}
          <Card>
            <CardHeader>
              <CardTitle>Ollama Configuration</CardTitle>
              <CardDescription>
                Connect to your local Ollama server for text generation and prompt creation.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ollamaUrl">Ollama URL</Label>
                  <Input
                    id="ollamaUrl"
                    type="url"
                    placeholder="http://localhost:11434"
                    value={settings.ollamaUrl}
                    onChange={(e) => updateSetting('ollamaUrl', e.target.value)}
                    disabled={loadState === 'loading' || saveState === 'saving'}
                    className={errors.ollamaUrl ? 'border-status-failed' : ''}
                  />
                {errors.ollamaUrl ? (
                  <p className="text-xs text-status-failed">{errors.ollamaUrl}</p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    The URL of your local Ollama server
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="modelName">Model Name</Label>
                  <Input
                    id="modelName"
                    placeholder="granite3.2:8b"
                    value={settings.modelName}
                    onChange={(e) => updateSetting('modelName', e.target.value)}
                    disabled={loadState === 'loading' || saveState === 'saving'}
                    className={errors.modelName ? 'border-status-failed' : ''}
                  />
                  {errors.modelName && (
                    <p className="text-xs text-status-failed">{errors.modelName}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="timeout">Timeout (seconds)</Label>
                  <Input
                    id="timeout"
                    type="number"
                    min={10}
                    max={600}
                    placeholder="120"
                    value={settings.timeout}
                    onChange={(e) => updateSetting('timeout', parseInt(e.target.value) || 0)}
                    disabled={loadState === 'loading' || saveState === 'saving'}
                    className={errors.timeout ? 'border-status-failed' : ''}
                  />
                  {errors.timeout && (
                    <p className="text-xs text-status-failed">{errors.timeout}</p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Image Generation */}
          <Card>
            <CardHeader>
              <CardTitle>Image Generation</CardTitle>
              <CardDescription>
                Configure the parameters for generating images from prompts.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="imageMode">Generation Mode</Label>
                <Select
                  value={settings.imageMode}
                  onValueChange={(value) => updateSetting('imageMode', value as Settings['imageMode'])}
                  disabled={loadState === 'loading' || saveState === 'saving'}
                >
                  <SelectTrigger id="imageMode" className="w-full">
                    <SelectValue placeholder="Choose generation mode" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="quality">Quality</SelectItem>
                    <SelectItem value="balanced">Balanced</SelectItem>
                    <SelectItem value="fast">Fast</SelectItem>
                    <SelectItem value="custom">Custom</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Quality and speed presets auto-tune model and parameters. Custom uses your manual model settings.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="imageModel">Image Model</Label>
                <Select
                  value={
                    useCustomModelInput || !IMAGE_MODEL_OPTIONS.some((option) => option.value === settings.imageModel)
                      ? '__custom__'
                      : settings.imageModel
                  }
                  onValueChange={(value) => {
                    if (value === '__custom__') {
                      setUseCustomModelInput(true)
                      return
                    }
                    setUseCustomModelInput(false)
                    updateSetting('imageModel', value)
                  }}
                  disabled={loadState === 'loading' || saveState === 'saving' || settings.imageMode !== 'custom'}
                >
                  <SelectTrigger id="imageModelPreset" className="w-full">
                    <SelectValue placeholder="Choose image model" />
                  </SelectTrigger>
                  <SelectContent>
                    {IMAGE_MODEL_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                    <SelectItem value="__custom__">Custom model...</SelectItem>
                  </SelectContent>
                </Select>
                {useCustomModelInput && (
                  <Input
                    id="imageModel"
                    placeholder="segmind/SSD-1B"
                    value={settings.imageModel}
                    onChange={(e) => updateSetting('imageModel', e.target.value)}
                    disabled={loadState === 'loading' || saveState === 'saving' || settings.imageMode !== 'custom'}
                    className={errors.imageModel ? 'border-status-failed' : ''}
                  />
                )}
                {errors.imageModel ? (
                  <p className="text-xs text-status-failed">{errors.imageModel}</p>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {settings.imageMode === 'custom'
                      ? 'The exact image model to use in custom mode'
                      : 'Preset mode controls model selection automatically'}
                  </p>
                )}
              </div>

              <Separator />

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="imageWidth">Width (px)</Label>
                  <Input
                    id="imageWidth"
                    type="number"
                    min={256}
                    max={2048}
                    step={64}
                    placeholder="1024"
                    value={settings.imageWidth}
                    onChange={(e) => updateSetting('imageWidth', parseInt(e.target.value) || 0)}
                    disabled={loadState === 'loading' || saveState === 'saving' || settings.imageMode !== 'custom'}
                    className={errors.imageWidth ? 'border-status-failed' : ''}
                  />
                  {errors.imageWidth && (
                    <p className="text-xs text-status-failed">{errors.imageWidth}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="imageHeight">Height (px)</Label>
                  <Input
                    id="imageHeight"
                    type="number"
                    min={256}
                    max={2048}
                    step={64}
                    placeholder="1024"
                    value={settings.imageHeight}
                    onChange={(e) => updateSetting('imageHeight', parseInt(e.target.value) || 0)}
                    disabled={loadState === 'loading' || saveState === 'saving' || settings.imageMode !== 'custom'}
                    className={errors.imageHeight ? 'border-status-failed' : ''}
                  />
                  {errors.imageHeight && (
                    <p className="text-xs text-status-failed">{errors.imageHeight}</p>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="imageSteps">Steps</Label>
                  <Input
                    id="imageSteps"
                    type="number"
                    min={1}
                    max={100}
                    placeholder="30"
                    value={settings.imageSteps}
                    onChange={(e) => updateSetting('imageSteps', parseInt(e.target.value) || 0)}
                    disabled={loadState === 'loading' || saveState === 'saving' || settings.imageMode !== 'custom'}
                    className={errors.imageSteps ? 'border-status-failed' : ''}
                  />
                  {errors.imageSteps ? (
                    <p className="text-xs text-status-failed">{errors.imageSteps}</p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      More steps = higher quality, slower
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="imageGuidance">Guidance Scale</Label>
                  <Input
                    id="imageGuidance"
                    type="number"
                    min={1}
                    max={20}
                    step={0.5}
                    placeholder="7.5"
                    value={settings.imageGuidance}
                    onChange={(e) => updateSetting('imageGuidance', parseFloat(e.target.value) || 0)}
                    disabled={loadState === 'loading' || saveState === 'saving' || settings.imageMode !== 'custom'}
                    className={errors.imageGuidance ? 'border-status-failed' : ''}
                  />
                  {errors.imageGuidance ? (
                    <p className="text-xs text-status-failed">{errors.imageGuidance}</p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Higher = more prompt adherence
                    </p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Save Button */}
          <div className="flex items-center justify-between pt-4">
            <div className="flex items-center gap-2 text-sm">
              {saveState === 'saved' && (
                <>
                  <Check className="h-4 w-4 text-status-image-ready" />
                  <span className="text-status-image-ready">Settings saved</span>
                </>
              )}
              {saveState === 'error' && (
                <>
                  <AlertCircle className="h-4 w-4 text-status-failed" />
                  <span className="text-status-failed">Failed to save</span>
                </>
              )}
            </div>
            <Button onClick={handleSave} disabled={loadState === 'loading' || saveState === 'saving'}>
              {loadState === 'loading'
                ? 'Loading...'
                : saveState === 'saving'
                ? 'Saving...'
                : 'Save Settings'}
            </Button>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
