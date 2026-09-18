import { useCallback, useEffect, useState } from 'react';

export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, interval = 0) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision(v => v + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    const run = async () => {
      try {
        const value = await load(controller.signal);
        if (!controller.signal.aborted) { setData(value); setError(''); }
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : '加载失败');
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          if (interval) timer = setTimeout(run, interval);
        }
      }
    };
    void run();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [load, interval, revision]);
  return { data, error, loading, refresh };
}
