"use client";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { CircleCheck, Info, TriangleAlert } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Kind = "success" | "error" | "info";
interface ToastItem { id: number; message: string; kind: Kind }
const Ctx = createContext<(message: string, kind?: Kind) => void>(() => {});
let seq = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const reduce = useReducedMotion();
  const show = useCallback((message: string, kind: Kind = "success") => {
    const id = ++seq;
    setItems((x) => [...x.slice(-3), { id, message, kind }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), 4500);
  }, []);
  const icon = { success: <CircleCheck size={18} className="text-ok" />, error: <TriangleAlert size={18} className="text-high" />, info: <Info size={18} className="text-accent" /> };
  return (
    <Ctx.Provider value={show}>
      {children}
      <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-0 bottom-20 z-[60] flex flex-col items-center gap-2 px-4 md:bottom-6">
        <AnimatePresence>
          {items.map((i) => (
            <motion.div key={i.id} initial={{ opacity: 0, y: reduce ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reduce ? 0 : 0.2 }}
              className="neu-raised pointer-events-auto flex max-w-md items-center gap-3 px-4 py-3 text-sm font-semibold" style={{ borderRadius: 12 }}>
              <span aria-hidden>{icon[i.kind]}</span>{i.message}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}
export const useToast = () => useContext(Ctx);
