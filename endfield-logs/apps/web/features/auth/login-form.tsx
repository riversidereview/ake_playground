"use client";

import { FormEvent, useEffect, useState } from "react";

import { buildApiUrl } from "../../lib/api/client";
import { useI18n } from "../../lib/i18n/context";

type AuthResponse = {
  status: "authenticated";
  user: {
    id: string;
    email: string;
    nickname: string;
    isAdmin: boolean;
  };
};

type SendCodeResponse = {
  ok: boolean;
  cooldownSeconds: number;
  debugCode?: string | null;
};

export function LoginForm() {
  const { t } = useI18n();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [codeSending, setCodeSending] = useState(false);
  const [codeCooldown, setCodeCooldown] = useState(0);

  useEffect(() => {
    if (codeCooldown <= 0) {
      return;
    }
    const timer = window.setTimeout(() => {
      setCodeCooldown((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [codeCooldown]);

  async function handleSendCode() {
    if (!email) {
      setMessage(t.auth.emailRequired);
      return;
    }

    setCodeSending(true);
    setMessage(null);
    try {
      const response = await fetch(buildApiUrl("/api/auth/send-code"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email,
          purpose: "web_login",
        }),
      });
      const data = (await response.json()) as SendCodeResponse | { error?: { message?: string } };
      if (!response.ok) {
        throw new Error(("error" in data && data.error?.message) || t.common.error);
      }
      const sendData = data as SendCodeResponse;
      setCodeCooldown(sendData.cooldownSeconds || 60);
      setMessage(sendData.debugCode ? `${t.auth.codeSent} (Dev: ${sendData.debugCode})` : t.auth.codeSent);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.common.error);
    } finally {
      setCodeSending(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (mode === "register" && password.length < 6) {
      setMessage(t.auth.passwordMinLength);
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const response = await fetch(buildApiUrl(endpoint), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: mode === "login" ? email : email || `${nickname}@local`,
          account: mode === "login" ? email : undefined,
          password,
          nickname: mode === "register" ? nickname : undefined,
          code: mode === "register" && verificationCode ? verificationCode : undefined,
          purpose: "web_login",
        }),
      });
      const data = (await response.json()) as
        | AuthResponse
        | { error?: { message?: string }; detail?: string | Array<{ msg?: string; loc?: string[] }> };
      if (!response.ok) {
        let errMsg = t.common.error;
        if ("error" in data && data.error?.message) {
          errMsg = data.error.message;
        } else if ("detail" in data) {
          if (typeof data.detail === "string") {
            errMsg = data.detail;
          } else if (Array.isArray(data.detail)) {
            errMsg = data.detail
              .map((d) => (d.msg ? (d.msg.includes("at least 6") ? t.auth.passwordMinLength : d.msg) : JSON.stringify(d)))
              .join("；");
          }
        }
        throw new Error(errMsg);
      }
      const authData = data as AuthResponse;
      setMessage(mode === "login" ? t.auth.loginSuccess : t.auth.registerSuccess);
      window.location.assign(authData.user.isAdmin ? "/admin" : "/manage");
      return;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t.common.error);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel auth-panel" style={{ display: "grid", gap: 16 }}>
      <div>
        <div className="eyebrow">{mode === "login" ? t.common.login : t.common.register}</div>
        <h2 style={{ margin: "6px 0 8px" }}>{mode === "login" ? t.auth.loginTitle : t.auth.registerTitle}</h2>
      </div>

      <div className="auth-tab-row">
        <button
          className={`button-chip${mode === "login" ? " is-active" : ""}`}
          onClick={() => {
            setMode("login");
            setMessage(null);
          }}
          type="button"
        >
          {t.common.login}
        </button>
        <button
          className={`button-chip${mode === "register" ? " is-active" : ""}`}
          onClick={() => {
            setMode("register");
            setMessage(null);
          }}
          type="button"
        >
          {t.common.register}
        </button>
      </div>

      <form className="panel-inset auth-form" onSubmit={handleSubmit}>
        {mode === "login" ? (
          <label className="field-stack">
            <span>{t.auth.accountOrEmailLabel}</span>
            <input
              autoComplete="username"
              className="field-input"
              onChange={(event) => setEmail(event.target.value)}
              placeholder={t.auth.accountOrEmailPlaceholder}
              type="text"
              value={email}
            />
          </label>
        ) : (
          <label className="field-stack">
            <span>{t.auth.nicknameLabel} {t.auth.usernameSuffix}</span>
            <input
              autoComplete="nickname"
              className="field-input"
              onChange={(event) => setNickname(event.target.value)}
              placeholder={t.auth.nicknamePlaceholder}
              value={nickname}
            />
          </label>
        )}

        <label className="field-stack">
          <span>{t.auth.passwordLabel}</span>
          <input
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            className="field-input"
            onChange={(event) => setPassword(event.target.value)}
            placeholder={mode === "register" ? t.auth.passwordRegisterPlaceholder : t.auth.passwordPlaceholder}
            type="password"
            value={password}
          />
        </label>

        <button
          className="button-primary"
          disabled={
            loading ||
            !password ||
            (mode === "login" ? !email : !nickname || nickname.trim().length < 2 || password.length < 6)
          }
          type="submit"
        >
          {loading
            ? `${t.common.loading}`
            : mode === "login"
              ? t.auth.loginButton
              : t.auth.registerButton}
        </button>
      </form>

      {message ? <p className="muted" style={{ margin: 0 }}>{message}</p> : null}
    </section>
  );
}
