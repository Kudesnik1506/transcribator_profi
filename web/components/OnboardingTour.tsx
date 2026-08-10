"use client";

import { useEffect, useState } from "react";

import { type OnboardingStep } from "@/lib/onboardingSteps";

const CARD_WIDTH = 320;
const SPOTLIGHT_PADDING = 8;

// The desktop nav collapses behind a hamburger below `lg` — its links stay
// mounted but shrink to a zero-size rect, so this naturally falls back to
// "not visible" there instead of highlighting something invisible.
function findVisibleTarget(navHref: string): DOMRect | null {
  const el = document.querySelector<HTMLElement>(`[data-tour-nav="${navHref}"]`);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0 ? rect : null;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

export function OnboardingTour({ steps, onFinish }: { steps: OnboardingStep[]; onFinish: () => void }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const step = steps[stepIndex];
  const isLastStep = stepIndex === steps.length - 1;

  useEffect(() => {
    function updateTarget() {
      setTargetRect(step.navHref ? findVisibleTarget(step.navHref) : null);
    }
    updateTarget();
    window.addEventListener("resize", updateTarget);
    return () => window.removeEventListener("resize", updateTarget);
  }, [step.navHref]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onFinish();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onFinish]);

  const cardStyle = targetRect
    ? {
        width: CARD_WIDTH,
        top: clamp(targetRect.bottom + 12, 12, window.innerHeight - 12),
        left: clamp(targetRect.left, 12, window.innerWidth - CARD_WIDTH - 12),
      }
    : undefined;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={step.title}
      onClick={onFinish}
      className={[
        "fixed inset-0 z-50",
        targetRect ? "" : "flex items-center justify-center bg-black/40 px-6",
      ].join(" ")}
    >
      {targetRect && (
        <div
          aria-hidden
          className="pointer-events-none fixed rounded-lg ring-2 ring-white transition-all duration-200"
          style={{
            top: targetRect.top - SPOTLIGHT_PADDING,
            left: targetRect.left - SPOTLIGHT_PADDING,
            width: targetRect.width + SPOTLIGHT_PADDING * 2,
            height: targetRect.height + SPOTLIGHT_PADDING * 2,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.55)",
          }}
        />
      )}

      <div
        onClick={(event) => event.stopPropagation()}
        style={cardStyle}
        className={[
          "flex flex-col gap-4 rounded-2xl border border-solid border-black/[.08] bg-background p-6 dark:border-white/[.145]",
          targetRect ? "fixed" : "w-full max-w-md",
        ].join(" ")}
      >
        <div className="flex items-center justify-center gap-1.5">
          {steps.map((_, index) => (
            <span
              key={index}
              className={[
                "h-1.5 w-1.5 rounded-full",
                index === stepIndex ? "bg-foreground" : "bg-black/[.15] dark:bg-white/[.2]",
              ].join(" ")}
            />
          ))}
        </div>

        <div className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold text-black dark:text-zinc-50">{step.title}</h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">{step.body}</p>
        </div>

        <div className="flex items-center justify-between pt-2">
          <button onClick={onFinish} className="text-sm text-zinc-500 underline hover:text-black dark:hover:text-zinc-50">
            Пропустить
          </button>
          <div className="flex gap-2">
            {stepIndex > 0 && (
              <button
                onClick={() => setStepIndex((index) => index - 1)}
                className="rounded-full border border-solid border-black/[.08] px-4 py-2 text-sm transition-colors hover:bg-black/[.04] dark:border-white/[.145] dark:hover:bg-[#1a1a1a]"
              >
                Назад
              </button>
            )}
            <button
              onClick={() => (isLastStep ? onFinish() : setStepIndex((index) => index + 1))}
              className="rounded-full bg-foreground px-4 py-2 text-sm text-background transition-colors hover:bg-[#383838] dark:hover:bg-[#ccc]"
            >
              {isLastStep ? "Понятно, начать" : "Далее"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
