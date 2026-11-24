import React, { useEffect, useState } from "react";
import { Image, ImageProps, Platform, View } from "react-native";
import { storage } from "@/src/utils/storage";
import { TOKEN_KEY } from "@/src/api";

/**
 * An <Image> for API routes that need the student's sign-in, such as
 * Wing photos (/api/wings/posts/{id}/image).
 *
 * A plain <Image source={{ uri }}> becomes an <img src> on web, which
 * cannot carry the Authorization header, so the server answers 401 and
 * the photo never shows. On web we fetch the bytes with the header and
 * display them from a local object URL (revoked on unmount). On iOS and
 * Android, <Image> accepts request headers directly.
 */
type Props = Omit<ImageProps, "source"> & { uri: string };

export function AuthImage({ uri, style, ...rest }: Props) {
  const [token, setToken] = useState<string | null>(null);
  const [webSrc, setWebSrc] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let objectUrl: string | null = null;
    (async () => {
      const t = await storage.secureGet<string>(TOKEN_KEY, "");
      if (!alive) return;
      setToken(t || "");
      if (Platform.OS !== "web" || !uri) return;
      try {
        const res = await fetch(uri, { headers: t ? { Authorization: `Bearer ${t}` } : {} });
        if (!res.ok) return;
        const blob = await res.blob();
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setWebSrc(objectUrl);
      } catch {
        // Leave the placeholder; the post card still shows its text.
      }
    })();
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [uri]);

  if (Platform.OS === "web") {
    return webSrc ? <Image source={{ uri: webSrc }} style={style} {...rest} /> : <View style={style} />;
  }
  if (token === null) return <View style={style} />;
  return (
    <Image
      source={{ uri, headers: token ? { Authorization: `Bearer ${token}` } : undefined }}
      style={style}
      {...rest}
    />
  );
}
