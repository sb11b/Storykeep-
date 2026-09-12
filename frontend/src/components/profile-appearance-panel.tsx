"use client";

import { toast } from "sonner";
import {
  BASE_FONT_SIZE_OPTIONS,
  FONT_FAMILY_OPTIONS,
  PAGE_COLOR_PRESETS,
  RAIL_COLOR_PRESETS,
  TOPBAR_COLOR_PRESETS,
  applyAppearance,
  type AppearanceSettings,
} from "@/lib/appearance";
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type ProfileAppearancePanelProps = {
  appearance: AppearanceSettings;
  readOnly: boolean;
  onChange: (next: AppearanceSettings) => void;
  onSaved: (preferences: Record<string, unknown>) => void;
};

function PresetRow({
  label,
  presets,
  value,
  custom,
  onPreset,
  onCustom,
  disabled,
}: {
  label: string;
  presets: Record<string, string>;
  value: string;
  custom: string | null;
  onPreset: (key: string) => void;
  onCustom: (hex: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex flex-wrap gap-2">
        {Object.entries(presets).map(([key, color]) => (
          <button
            key={key}
            type="button"
            disabled={disabled}
            title={key}
            onClick={() => onPreset(key)}
            className={cn(
              "size-8 rounded-md border-2",
              value === key && !custom ? "border-primary ring-2 ring-primary/30" : "border-border",
            )}
            style={{ background: color }}
          />
        ))}
      </div>
      <Input
        placeholder="Custom hex (#aabbcc)"
        value={custom || ""}
        disabled={disabled}
        onChange={(event) => onCustom(event.target.value)}
      />
    </div>
  );
}

export function ProfileAppearancePanel({ appearance, readOnly, onChange, onSaved }: ProfileAppearancePanelProps) {
  async function saveAppearance() {
    try {
      const preferences = await api.updatePreferences({ appearance });
      applyAppearance(appearance);
      onSaved(preferences);
      toast.success("Appearance saved");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not save appearance");
    }
  }

  function patch(next: Partial<AppearanceSettings>) {
    const merged = { ...appearance, ...next };
    onChange(merged);
    applyAppearance(merged);
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Theme colors</CardTitle>
          <CardDescription>Page background, left rail, and top bar. Pick a preset or enter a custom hex.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <PresetRow
            label="Page background"
            presets={PAGE_COLOR_PRESETS}
            value={appearance.page_preset}
            custom={appearance.page_custom}
            disabled={readOnly}
            onPreset={(key) => patch({ page_preset: key, page_custom: null })}
            onCustom={(hex) => patch({ page_custom: hex || null })}
          />
          <PresetRow
            label="Left rail"
            presets={RAIL_COLOR_PRESETS}
            value={appearance.rail_preset}
            custom={appearance.rail_custom}
            disabled={readOnly}
            onPreset={(key) => patch({ rail_preset: key, rail_custom: null })}
            onCustom={(hex) => patch({ rail_custom: hex || null })}
          />
          <PresetRow
            label="Top bar"
            presets={TOPBAR_COLOR_PRESETS}
            value={appearance.topbar_preset}
            custom={appearance.topbar_custom}
            disabled={readOnly}
            onPreset={(key) => patch({ topbar_preset: key, topbar_custom: null })}
            onCustom={(hex) => patch({ topbar_custom: hex || null })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Typography</CardTitle>
          <CardDescription>Base font for chrome and reader. Article text size can still override locally.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Font family</Label>
            <div className="flex flex-wrap gap-2">
              {FONT_FAMILY_OPTIONS.map((option) => (
                <Button
                  key={option.value}
                  type="button"
                  size="sm"
                  variant={appearance.font_family === option.value ? "default" : "outline"}
                  disabled={readOnly}
                  onClick={() => patch({ font_family: option.value })}
                >
                  {option.label}
                </Button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <Label>Base font size</Label>
            <div className="flex flex-wrap gap-2">
              {BASE_FONT_SIZE_OPTIONS.map((option) => (
                <Button
                  key={option.value}
                  type="button"
                  size="sm"
                  variant={appearance.base_font_size === option.value ? "default" : "outline"}
                  disabled={readOnly}
                  onClick={() => patch({ base_font_size: option.value })}
                >
                  {option.label}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {!readOnly ? (
        <Button type="button" onClick={() => void saveAppearance()}>
          Save appearance
        </Button>
      ) : null}
    </div>
  );
}
