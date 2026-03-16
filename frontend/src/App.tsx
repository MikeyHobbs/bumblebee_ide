import { useState, useCallback } from "react";
import LandingPage from "@/components/LandingPage";
import Layout from "@/components/Layout";
import { useWebSocket } from "@/hooks/useWebSocket";

function App() {
  const [indexed, setIndexed] = useState(false);

  useWebSocket();

  const handleIndexed = useCallback(() => {
    setIndexed(true);
  }, []);

  if (!indexed) {
    return <LandingPage onIndexed={handleIndexed} />;
  }

  return <Layout />;
}

export default App;
