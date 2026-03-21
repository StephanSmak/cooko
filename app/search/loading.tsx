export default function SearchLoading() {
  return (
    <div className="space-y-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="animate-pulse overflow-hidden rounded-xl border"
          style={{ borderColor: "#e5e7eb", backgroundColor: "#ffffff" }}
        >
          {/* Header skeleton */}
          <div
            className="flex items-center justify-between px-5 py-4"
            style={{ borderBottom: "1px solid #f3f4f6" }}
          >
            <div className="space-y-2">
              <div
                className="h-4 w-48 rounded"
                style={{ backgroundColor: "#f3f4f6" }}
              />
              <div
                className="h-3 w-20 rounded"
                style={{ backgroundColor: "#f9fafb" }}
              />
            </div>
            <div
              className="h-5 w-16 rounded"
              style={{ backgroundColor: "#f3f4f6" }}
            />
          </div>

          {/* Row skeletons */}
          {Array.from({ length: i === 0 ? 3 : 2 }).map((_, j) => (
            <div
              key={j}
              className="flex items-center gap-3 px-5 py-3"
              style={{
                borderLeft: "3px solid transparent",
                borderTop: j > 0 ? "1px solid #f9fafb" : undefined,
              }}
            >
              <div
                className="h-5 w-16 rounded"
                style={{ backgroundColor: "#f3f4f6" }}
              />
              <div className="flex-1">
                <div
                  className="h-3 w-3/4 rounded"
                  style={{ backgroundColor: "#f9fafb" }}
                />
              </div>
              <div className="space-y-1 text-right">
                <div
                  className="ml-auto h-4 w-16 rounded"
                  style={{ backgroundColor: "#f3f4f6" }}
                />
                <div
                  className="ml-auto h-3 w-20 rounded"
                  style={{ backgroundColor: "#f9fafb" }}
                />
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
