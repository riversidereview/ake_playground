"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useI18n } from "../lib/i18n/context";

const AFDIAN_URL = "https://afdian.com/a/zhfdy";

export function AboutDialog() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    const triggerElement = triggerRef.current;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const focusableElements = dialogRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusableElements?.length) {
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
      triggerElement?.focus();
    };
  }, [open]);

  return (
    <>
      <button
        aria-controls="about-dialog"
        aria-expanded={open}
        aria-haspopup="dialog"
        className={`nav-link about-dialog-trigger${open ? " is-active" : ""}`}
        onClick={() => setOpen(true)}
        ref={triggerRef}
        type="button"
      >
        {t.common.about}
      </button>
      {open
        ? createPortal(
            <div
              className="about-dialog-backdrop"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) {
                  setOpen(false);
                }
              }}
            >
              <div
                aria-describedby="about-dialog-description"
                aria-labelledby="about-dialog-title"
                aria-modal="true"
                className="about-dialog"
                id="about-dialog"
                ref={dialogRef}
                role="dialog"
              >
                <header className="about-dialog-header">
                  <div>
                    <span className="eyebrow">{t.about.aboutSite}</span>
                    <h2 id="about-dialog-title">{t.common.siteTitle}</h2>
                    <p>{t.about.tagline}</p>
                  </div>
                  <button
                    aria-label={t.common.close}
                    className="about-dialog-close"
                    onClick={() => setOpen(false)}
                    ref={closeButtonRef}
                    type="button"
                  >
                    ×
                  </button>
                </header>

                <p className="about-dialog-description" id="about-dialog-description">
                  {t.about.description}
                </p>

                <ul className="about-dialog-features" aria-label={t.about.featuresTitle}>
                  <li>{t.about.feature1}</li>
                  <li>{t.about.feature2}</li>
                  <li>{t.about.feature3}</li>
                </ul>

                <section className="about-dialog-support" aria-labelledby="about-dialog-support-title">
                  <div>
                    <span className="eyebrow">{t.about.supportTitle}</span>
                    <h3 id="about-dialog-support-title">{t.about.supportHeading}</h3>
                    <p>{t.about.supportDescription}</p>
                  </div>
                  <a className="afdian-support-link" href={AFDIAN_URL} rel="noreferrer noopener" target="_blank">
                    <span className="afdian-support-mark" aria-hidden="true">
                      ⚡
                    </span>
                    <span>{t.about.supportButton}</span>
                    <span className="afdian-support-arrow" aria-hidden="true">
                      ↗
                    </span>
                  </a>
                </section>
              </div>
            </div>,
            document.body,
          )
        : null}
      </>
  );
}
