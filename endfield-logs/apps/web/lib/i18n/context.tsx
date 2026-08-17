"use client";

import React, { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { enDictionary } from "./en";
import { zhDictionary } from "./zh";
import type { Dictionary, Locale } from "./types";

export function getDictionary(locale: Locale): Dictionary {
  return locale === "zh" ? zhDictionary : enDictionary;
}

type I18nContextType = {
  locale: Locale;
  t: Dictionary;
  dict: Dictionary;
  setLocale: (locale: Locale) => void;
};

const I18nContext = createContext<I18nContextType>({
  locale: "en",
  t: enDictionary,
  dict: enDictionary,
  setLocale: () => {},
});

const STORAGE_KEY = "endfield_locale";
const COOKIE_KEY = "NEXT_LOCALE";

function getInitialLocale(): Locale {
  if (typeof window === "undefined") {
    return "en";
  }
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "zh") {
    return stored;
  }
  const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE_KEY}=([^;]*)`));
  if (match && (match[1] === "en" || match[1] === "zh")) {
    return match[1] as Locale;
  }
  return "en";
}

export function I18nProvider({
  children,
  initialLocale = "en",
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    const active = getInitialLocale();
    if (active !== locale) {
      setLocaleState(active);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale);
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, newLocale);
      document.cookie = `${COOKIE_KEY}=${newLocale}; path=/; max-age=31536000; SameSite=Lax`;
      document.documentElement.lang = newLocale === "zh" ? "zh-CN" : "en";
    }
  };

  const dictionary = getDictionary(locale);
  const value = {
    locale,
    t: dictionary,
    dict: dictionary,
    setLocale,
  };

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  return context;
}
