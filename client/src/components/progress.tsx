// Fixed typing and basic UI
type StatusType = {
  status: "" | "PENDING" | "SCRAPING" | "PROCESSING" | "GENERATING" | "COMPLETED" | "FAILED";
  progress: number;
};

export default function ProgressBar({ status, progress }: StatusType) {
  return (
    <div className="w-full max-w-md">
      <p className="mb-1 text-sm font-medium">{status}</p>
      <div className="w-full bg-gray-200 rounded-full h-4">
        <div
          className={`h-4 rounded-full ${
            status === "FAILED" ? "bg-red-500" : status === "COMPLETED" ? "bg-green-500" : "bg-pink-500"
          }`}
          style={{ width: `${progress}%` }}
        ></div>
      </div>
    </div>
  );
}
