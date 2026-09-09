"use client";

import { Mail, MessageSquare, Share2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { openArticleShare, type ShareArticle } from "@/lib/share";

const SHARE_OPTIONS = [
  { target: "email" as const, label: "Email", icon: Mail },
  { target: "sms" as const, label: "Text message", icon: MessageSquare },
  { target: "facebook" as const, label: "Facebook", icon: Share2 },
  { target: "x" as const, label: "X", icon: Share2 },
  { target: "reddit" as const, label: "Reddit", icon: Share2 },
];

export function ArticleShareMenu({ article }: { article: ShareArticle }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button size="sm" variant="outline" aria-label="Share article">
            <Share2 className="size-3.5" />
            Share
          </Button>
        }
      />
      <DropdownMenuContent align="start" className="min-w-44">
        <DropdownMenuLabel>Share this article</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {SHARE_OPTIONS.map((item) => (
          <DropdownMenuItem key={item.target} onClick={() => openArticleShare(item.target, article)}>
            <item.icon className="size-4" />
            {item.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
