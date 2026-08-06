import { useMutation, useQuery } from "@tanstack/react-query";
import {
  getOllamaModels,
  getSettings,
  MODE_PRESETS,
  saveSettings,
  Settings,
} from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import PageHeader from "@/components/PageHeader";

export default function SettingsPage() {
  const { data: initial, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });
  const { data: modelsData } = useQuery({
    queryKey: ["ollama-models"],
    queryFn: getOllamaModels,
    enabled: initial?.llmProvider === "ollama",
  });

  const [s, setS] = useState<Settings | null>(null);
  useEffect(() => {
    if (initial && !s) setS(initial);
  }, [initial, s]);

  const mut = useMutation({
    mutationFn: (payload: Settings) => saveSettings(payload),
    onSuccess: (r) => {
      toast.success("Settings saved");
      setS(r);
    },
    onError: (e) => toast.error((e as { message?: string })?.message ?? "Save failed"),
  });

  if (isLoading || !s) {
    return (
      <div className="p-8">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const update = <K extends keyof Settings>(k: K, v: Settings[K]) =>
    setS({ ...s, [k]: v });

  const onModeChange = (mode: Settings["imageMode"]) => {
    if (mode === "custom") {
      update("imageMode", "custom");
    } else {
      const preset = MODE_PRESETS[mode];
      setS({ ...s, imageMode: mode, ...preset });
    }
  };

  const customDisabled = s.imageMode !== "custom";

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6 md:p-8">
      <PageHeader
        kicker="Configuration"
        title="Settings"
        subtitle="Configure AI providers and image generation."
      />

      <Card className="p-6 space-y-4 shadow-card">
        <h2 className="font-semibold text-lg">Language Model</h2>
        <div className="grid gap-2">
          <Label>Active provider</Label>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center rounded-sm border border-border bg-muted px-2 py-1 font-mono text-xs uppercase tracking-wide text-foreground">
              {s.llmProvider}
            </span>
            <span className="text-sm text-muted-foreground">{s.llmModel}</span>
          </div>
          <p className="text-xs text-muted-foreground">
            Set via the <code>LLM_PROVIDER</code> environment variable on the backend — not
            editable here.
          </p>
        </div>

        {s.llmProvider === "ollama" && (
          <>
            <div className="grid gap-2">
              <Label>Ollama URL</Label>
              <Input value={s.ollamaUrl} readOnly className="bg-muted" />
            </div>
            <div className="grid gap-2">
              <Label>LLM Model</Label>
              <Select value={s.modelName} onValueChange={(v) => update("modelName", v)}>
                <SelectTrigger>
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {(modelsData?.models ?? [s.modelName]).filter(Boolean).map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2">
              <Label>Timeout (sec)</Label>
              <Input
                type="number"
                value={s.timeout}
                onChange={(e) => update("timeout", Number(e.target.value))}
              />
            </div>
          </>
        )}
      </Card>

      <Card className="p-6 space-y-4 shadow-card">
        <h2 className="font-semibold text-lg">Image Generation</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label>Image Mode</Label>
            <Select value={s.imageMode} onValueChange={(v) => onModeChange(v as Settings["imageMode"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(["quality", "balanced", "fast", "custom"] as const).map((m) => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Artistic Style</Label>
            <Select value={s.imageStyle} onValueChange={(v) => update("imageStyle", v as Settings["imageStyle"])}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(["normal", "storybook", "comic", "cinematic"] as const).map((m) => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="grid gap-2">
          <Label>Image Model</Label>
          <Input
            value={s.imageModel}
            disabled={customDisabled}
            onChange={(e) => update("imageModel", e.target.value)}
          />
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label>Width</Label>
            <Input
              type="number"
              value={s.imageWidth}
              disabled={customDisabled}
              onChange={(e) => update("imageWidth", Number(e.target.value))}
            />
          </div>
          <div className="grid gap-2">
            <Label>Height</Label>
            <Input
              type="number"
              value={s.imageHeight}
              disabled={customDisabled}
              onChange={(e) => update("imageHeight", Number(e.target.value))}
            />
          </div>
          <div className="grid gap-2">
            <Label>Steps</Label>
            <Input
              type="number"
              value={s.imageSteps}
              disabled={customDisabled}
              onChange={(e) => update("imageSteps", Number(e.target.value))}
            />
          </div>
          <div className="grid gap-2">
            <Label>Guidance</Label>
            <Input
              type="number"
              step="0.1"
              value={s.imageGuidance}
              disabled={customDisabled}
              onChange={(e) => update("imageGuidance", Number(e.target.value))}
            />
          </div>
        </div>
      </Card>

      <div className="flex justify-end">
        <Button
          className="bg-gradient-primary"
          disabled={mut.isPending}
          onClick={() => mut.mutate(s)}
        >
          {mut.isPending ? "Saving..." : "Save changes"}
        </Button>
      </div>
    </div>
  );
}
