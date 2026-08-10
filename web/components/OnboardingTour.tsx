"use client";

import { useEffect, useState } from "react";

import { type OnboardingStep } from "@/lib/onboardingSteps";

export function OnboardingTour({ steps, onFinish }: { steps: OnboardingStep[]; onFinish: () => void }) {
  const [stepIndex, setStepIndex] = useState(0);
  const step = steps[stepIndex];
  const isLastStep = stepIndex === steps.length - 1;

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onFinish();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onFinish]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={step.title}
      onClick={onFinish}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-6"
    >
      <div
        onClick={(event) => event.stopPropagation()}
        className="flex w-full max-w-md flex-col gap-4 rounded-2xl border border-solid border-black/[.08] bg-background p-6 dark:border-white/[.145]"
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
