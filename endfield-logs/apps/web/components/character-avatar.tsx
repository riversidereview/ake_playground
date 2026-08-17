"use client";

import { useEffect, useState } from "react";
import { useI18n } from "../lib/i18n/context";
import { getCharacterAvatarUrl, getCharacterRemoteAvatarUrl, getLocalizedCharacterName, resolveAssetUrl } from "../lib/i18n/terms";

type CharacterAvatarProps = {
  name: string;
  characterKey?: string | null;
  avatarUrl?: string | null;
  size?: "sm" | "md" | "lg";
};

export function CharacterAvatar({ name, characterKey, avatarUrl, size = "md" }: CharacterAvatarProps) {
  const { locale } = useI18n();
  const displayName = getLocalizedCharacterName(name || characterKey, locale) || name || "?";
  const resolvedPrimary = resolveAssetUrl(avatarUrl) || getCharacterAvatarUrl(name, characterKey);
  const [currentSrc, setCurrentSrc] = useState<string | null>(resolvedPrimary);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const nextPrimary = resolveAssetUrl(avatarUrl) || getCharacterAvatarUrl(name, characterKey);
    setCurrentSrc(nextPrimary);
    setFailed(false);
  }, [avatarUrl, name, characterKey]);

  const initial = displayName.slice(0, 1).toUpperCase();
  const showImage = Boolean(currentSrc) && !failed;

  function handleError() {
    const remoteFallback = getCharacterRemoteAvatarUrl(name, characterKey);
    if (remoteFallback && currentSrc !== remoteFallback) {
      setCurrentSrc(remoteFallback);
    } else {
      setFailed(true);
    }
  }

  return (
    <span className={`character-avatar character-avatar-${size}`} title={displayName}>
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          alt={displayName}
          className="character-avatar-image"
          decoding="async"
          loading="lazy"
          onError={handleError}
          src={currentSrc ?? undefined}
        />
      ) : (
        <span className="character-avatar-fallback">{initial}</span>
      )}
    </span>
  );
}


