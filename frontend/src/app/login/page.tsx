"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError, api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function handleLogin(form: FormData) {
    setBusy(true);
    try {
      await api.login(String(form.get("email")), String(form.get("password")));
      router.replace("/");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not sign in");
    } finally {
      setBusy(false);
    }
  }

  async function handleRegister(form: FormData) {
    setBusy(true);
    try {
      await api.register(
        String(form.get("email")),
        String(form.get("password")),
        String(form.get("display_name") || "") || undefined,
      );
      router.replace("/");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not create account");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#f3e3c8_0%,transparent_42%),linear-gradient(180deg,#f6f1e8, #efe6d6)] flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <p className="font-[family-name:var(--font-serif)] text-4xl tracking-tight">Storykeep</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Keep the stories that matter. Search them decades from now.
          </p>
        </div>
        <Card className="shadow-none border-border/80">
          <CardHeader>
            <CardTitle className="font-[family-name:var(--font-serif)] text-2xl">Open your archive</CardTitle>
            <CardDescription>
              Demo account: <span className="font-medium text-foreground">steve@storykeep.local</span> / commonplace
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="login">
              <TabsList className="w-full">
                <TabsTrigger value="login" className="flex-1">
                  Sign in
                </TabsTrigger>
                <TabsTrigger value="register" className="flex-1">
                  Create account
                </TabsTrigger>
              </TabsList>
              <TabsContent value="login" className="pt-4">
                <form
                  className="space-y-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void handleLogin(new FormData(event.currentTarget));
                  }}
                >
                  <div className="space-y-1.5">
                    <Label htmlFor="login-email">Email</Label>
                    <Input id="login-email" name="email" type="email" required defaultValue="steve@storykeep.local" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="login-password">Password</Label>
                    <Input id="login-password" name="password" type="password" required defaultValue="commonplace" />
                  </div>
                  <Button type="submit" className="w-full" disabled={busy}>
                    {busy ? "Opening…" : "Enter the library"}
                  </Button>
                </form>
              </TabsContent>
              <TabsContent value="register" className="pt-4">
                <form
                  className="space-y-3"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void handleRegister(new FormData(event.currentTarget));
                  }}
                >
                  <div className="space-y-1.5">
                    <Label htmlFor="reg-name">Name</Label>
                    <Input id="reg-name" name="display_name" placeholder="Steve" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="reg-email">Email</Label>
                    <Input id="reg-email" name="email" type="email" required />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="reg-password">Password</Label>
                    <Input id="reg-password" name="password" type="password" minLength={8} required />
                  </div>
                  <Button type="submit" className="w-full" disabled={busy}>
                    {busy ? "Creating…" : "Start an archive"}
                  </Button>
                </form>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
