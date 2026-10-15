import type { staffRequest } from "../api";

export type Call = <T>(path: string, init?: Parameters<typeof staffRequest>[2]) => Promise<T>;
