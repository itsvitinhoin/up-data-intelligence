"use client";
import { useRef, useState } from "react";
import Image from "next/image";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
export function LogoUpload({
  value,
  onChange,
  onBusy,
}: {
  value: string;
  onChange: (v: string) => void;
  onBusy: (v: boolean) => void;
}) {
  const [error, setError] = useState("");
  const sequence = useRef(0);
  return (
    <div className="form-field">
      <Label htmlFor="brand-logo">Logo da marca</Label>
      <Input
        id="brand-logo"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          const current = ++sequence.current;
          onChange("");
          setError("");
          onBusy(false);
          if (!file) return;
          if (
            !["image/png", "image/jpeg", "image/webp"].includes(file.type) ||
            file.size > 2 * 1024 * 1024
          ) {
            setError("Use PNG, JPEG ou WebP de até 2 MB.");
            e.target.value = "";
            return;
          }
          onBusy(true);
          try {
            const bitmap = await createImageBitmap(file);
            const canvas = document.createElement("canvas");
            const scale = Math.min(
              1,
              512 / Math.max(bitmap.width, bitmap.height),
            );
            canvas.width = Math.max(1, Math.round(bitmap.width * scale));
            canvas.height = Math.max(1, Math.round(bitmap.height * scale));
            const ctx = canvas.getContext("2d");
            if (!ctx) throw new Error("canvas");
            ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
            bitmap.close();
            if (current === sequence.current)
              onChange(canvas.toDataURL("image/png"));
          } catch {
            if (current === sequence.current)
              setError("Arquivo de imagem inválido. Escolha outra imagem.");
          } finally {
            if (current === sequence.current) onBusy(false);
          }
        }}
      />
      <small className="muted">
        PNG, JPEG ou WebP · até 2 MB. Salvo apenas nesta sessão demonstrativa.
      </small>
      {error && <small role="alert">{error}</small>}
      {value && (
        <div className="logo-preview">
          <Image
            src={value}
            alt="Prévia da logo"
            width={64}
            height={64}
            unoptimized
          />
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              ++sequence.current;
              onChange("");
              onBusy(false);
            }}
          >
            Remover logo
          </Button>
        </div>
      )}
    </div>
  );
}
