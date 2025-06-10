"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import ProgressBar from "@/components/progress";

export default function Home() {
  const ws = useRef<WebSocket | null>(null);
  const [userInput, setUserInput] = useState<string>(
    "https://tailwindcss.com"
  );
  // https://quotes.toscrape.com/
  const [status, setStatus] = useState<
    | ""
    | "PENDING"
    | "SCRAPING"
    | "PROCESSING"
    | "GENERATING"
    | "COMPLETED"
    | "FAILED"
  >("");
  const [progress, setProgress] = useState<number>(0);
  const [generatedHtml, setGeneratedHtml] = useState<string>("");
  const [iframeUrl, setIframeUrl] = useState<string>("");

  const cloneWebsite = async () => {
    console.log("cloning", userInput);

    // Reset previous state
    setGeneratedHtml("");
    setIframeUrl("");

    const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND}/api/clone`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: userInput }),
    });

    const data = await res.json();

    console.log(data);
    const jobId = data.job_id as string;

    // Open a single WebSocket for this job_id
    const backendHost = process.env.NEXT_PUBLIC_BACKEND!.replace(
      /^https?:\/\//,
      ""
    );
    ws.current = new WebSocket(`ws://${backendHost}/ws/clone/${jobId}`);

    setStatus("PENDING");
    setProgress(0);

    ws.current.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as {
          status?: string;
          progress?: number;
        };

        console.log("WS update:", msg);

        if (typeof msg.progress === "number") {
          setProgress(msg.progress);
        }

        if (msg.status) {
          setStatus(msg.status.toUpperCase() as any);

          // Fetch HTML when completed
          if (msg.status.toUpperCase() === "COMPLETED") {
            const getHTML = async () => {
              try {
                const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND}/api/clone/${jobId}/result`);
                const data = await res.json();

                console.log("DATA:", data);
                console.log("Generated HTML:", data.generated_html);

                // Set the HTML and create blob URL for iframe
                const htmlContent = data.generated_html;
                setGeneratedHtml(htmlContent);

                // Create blob URL for iframe
                const blob = new Blob([htmlContent], { type: 'text/html' });
                const url = URL.createObjectURL(blob);
                setIframeUrl(url);

              } catch (error) {
                console.error("Error fetching HTML:", error);
              }
            };

            getHTML();
          }
        }
      } catch (e) {
        console.error("WebSocket invalid JSON:", event.data, "error: ", e);
      }
    };

    ws.current.onopen = () => {
      console.log("WebSocket opened for job:", jobId);
      ws.current!.send("test");
    };
    ws.current.onclose = () => {
      console.log("WebSocket closed");
    };
    ws.current.onerror = (err) => {
      console.error("WebSocket error:", err);
    };
  };

  // Clean up blob URL when component unmounts or new HTML is generated
  const cleanupBlobUrl = useCallback(() => {
    if (iframeUrl) {
      URL.revokeObjectURL(iframeUrl);
    }
  }, [iframeUrl]);

  // Clean up on component unmount
  useEffect(() => {
    return () => {
      cleanupBlobUrl();
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [cleanupBlobUrl]);

  // Clean up previous blob URL when creating new one
  useEffect(() => {
    return cleanupBlobUrl;
  }, [iframeUrl, cleanupBlobUrl]);

  return (
    <div className="w-screen h-screen min-h-screen relative bg-[url('/bg1.png')] bg-cover bg-center">
      <div className="flex w-full items-center justify-center">
        <div className="p-5 flex items-center justify-center flex-col gap-3 w-[90%] bg-pink-200/70 rounded-b-xl">
          <h1 className="font-bold text-transparent text-2xl bg-clip-text bg-linear-to-r from-pink-400/80 via-pink-800/70 to-pink-600/70 animate-gradient-x">orchids-challenge</h1>

          <Input
            type="text"
            placeholder="url"
            value={userInput}
            onChange={(e: any) => {
              setUserInput(e.target.value);
            }}
            className="bg-pink-100 w-[50%]"
          />
          <Button
            className="cursor-pointer bg-pink-200/80 hover:bg-pink-200/70 font-semibold "
            variant={"secondary"}
            onClick={cloneWebsite}
          >
            <h1 className="text-transparent bg-clip-text bg-linear-to-r from-pink-600/70 via-pink-800/70 to-pink-400/80 animate-gradient-x">CLONE!</h1>
          </Button>

          <ProgressBar status={status} progress={progress} />
        </div>
      </div>

      {/* Iframe to display generated HTML */}
      <div className="h-[70vh] w-full p-4 overflow-auto">
        {iframeUrl ? (
          <iframe
            src={iframeUrl}
            className="w-full h-full border border-gray-300 rounded-lg shadow-lg"
            title="Cloned Website"
          />
        ) : (
          <div className="w-full h-full border border-pink-300 rounded-lg shadow-lg bg-pink-200/80 flex items-center justify-center">
            <p className="text-transparent bg-clip-text bg-linear-to-r from-pink-600/70 via-pink-800/70 to-pink-400/80 animate-gradient-x">
              {status === "COMPLETED" ? "Loading HTML..." : "Generated website will appear here"}
            </p>
          </div>
        )}
      </div>

      {generatedHtml && (
        <div className="fixed bottom-4 right-4">
          <Button
            onClick={() => {
              const element = document.createElement("a");
              const file = new Blob([generatedHtml], { type: 'text/html' });
              element.href = URL.createObjectURL(file);
              element.download = "cloned-website.html";
              document.body.appendChild(element);
              element.click();
              document.body.removeChild(element);
              URL.revokeObjectURL(element.href);
            }}
            className="bg-pink-200/90 hover:bg-pink-200/80 text-black"
          >
            Download HTML
          </Button>
        </div>
      )}
    </div>
  );
}