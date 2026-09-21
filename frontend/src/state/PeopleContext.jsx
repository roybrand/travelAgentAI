import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { people } from "../api";

const Ctx = createContext(null);
export const usePeople = () => useContext(Ctx);

const KEY = "wf.people.v1";
const load = () => {
  try {
    return localStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
};
const save = (t) => {
  try {
    if (t) localStorage.setItem(KEY, t);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage may be unavailable */
  }
};

/** The signed-in traveler (Wayfinder People), their plans and open requests. Separate from partner accounts. */
export function PeopleProvider({ children }) {
  const [token, setToken] = useState(load);
  const [state, setState] = useState({ me: null, plans: [], requests: [], blocked: [] });
  const [options, setOptions] = useState(null);

  useEffect(() => {
    people.options().then(setOptions).catch(() => {});
  }, []);

  const signOut = useCallback(() => {
    const t = load();
    if (t) people.logout(t);
    save("");
    setToken("");
    setState({ me: null, plans: [], requests: [], blocked: [] });
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    try {
      const r = await people.me(token);
      setState({ me: r.me, plans: r.plans, requests: r.requests, blocked: r.blocked });
    } catch (e) {
      if (e.status === 401) signOut();
    }
  }, [token, signOut]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signIn = useCallback((t) => {
    save(t);
    setToken(t);
  }, []);

  return <Ctx.Provider value={{ token, ...state, options, refresh, signIn, signOut }}>{children}</Ctx.Provider>;
}
