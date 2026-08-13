import os

file_path = r"d:\program\chat\frontend\src\App.tsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add states
state_target = "const [isAuthOpen, setIsAuthOpen] = useState(false);"
state_replacement = """const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [backendStatus, setBackendStatus] = useState<"online" | "offline" | "checking">("checking");"""

if "const [backendStatus, setBackendStatus]" not in content:
    content = content.replace(state_target, state_replacement)

# Add ping logic in useEffect
ping_target = """  useEffect(() => {
    if (window.innerWidth >= 768) {
      setIsSidebarOpen(true);
    }
  }, []);"""

ping_replacement = """  useEffect(() => {
    if (window.innerWidth >= 768) {
      setIsSidebarOpen(true);
    }
    
    // Check backend status
    const checkBackend = async () => {
      try {
        const res = await fetch(getApiUrl("/api/ping"));
        if (res.ok) {
          setBackendStatus("online");
        } else {
          setBackendStatus("offline");
        }
      } catch (e) {
        setBackendStatus("offline");
      }
    };
    checkBackend();
    const interval = setInterval(checkBackend, 10000);
    return () => clearInterval(interval);
  }, []);"""

if "checkBackend = async () =>" not in content:
    content = content.replace(ping_target, ping_replacement)

# Add banner in UI
banner_target = """        {/* メインチャットエリア */}
        <div className="flex-1 flex flex-col min-w-0 bg-[#0b0e14] relative">"""

banner_replacement = """        {/* メインチャットエリア */}
        <div className="flex-1 flex flex-col min-w-0 bg-[#0b0e14] relative">
          {backendStatus === "offline" && (
            <div className="absolute top-0 left-0 right-0 z-50 bg-amber-500/90 text-white text-xs font-bold py-2 px-4 flex justify-between items-center shadow-md animate-in slide-in-from-top">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                Backend is currently offline or waking up from cold start. Please wait...
              </div>
            </div>
          )}"""

if "backendStatus === \"offline\"" not in content:
    content = content.replace(banner_target, banner_replacement)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("App.tsx patched successfully.")
