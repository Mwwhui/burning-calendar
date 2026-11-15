"use client";

import { Check, Undo2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { DrawMode } from "@/features/explorer/store";

/** Instructions and actions while drawing an own area. */
export function DrawBar({
  mode,
  points,
  onFinish,
  onUndo,
  onCancel,
}: {
  mode: DrawMode;
  points: number;
  onFinish: () => void;
  onUndo: () => void;
  onCancel: () => void;
}) {
  const hint =
    mode === "rectangle"
      ? points === 0
        ? "Click one corner of your area"
        : "Click the opposite corner"
      : points < 3
        ? "Click to add corners of your area"
        : "Keep clicking, or click the first corner / double-click to finish";
  return (
    <div className="absolute top-14 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border bg-background/95 py-1.5 pr-1.5 pl-4 text-sm shadow-lg backdrop-blur">
      <span className="text-muted-foreground">{hint}</span>
      {mode === "polygon" && points > 0 && (
        <Button size="icon-sm" variant="ghost" onClick={onUndo} aria-label="Remove last corner">
          <Undo2 />
        </Button>
      )}
      {mode === "polygon" && points >= 3 && (
        <Button size="sm" onClick={onFinish} className="rounded-full">
          <Check /> Done
        </Button>
      )}
      <Button size="icon-sm" variant="ghost" onClick={onCancel} aria-label="Stop drawing">
        <X />
      </Button>
    </div>
  );
}
