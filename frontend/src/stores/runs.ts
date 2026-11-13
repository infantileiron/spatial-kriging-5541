import {entityStore} from "./entity";
import {cancelRun,retryRun} from "../api/runs";
export const runs=entityStore("runs");
// 取消/重试均为后端幂等操作；动作后立即刷新，轮询会继续追踪新尝试
export async function cancel(id:string){await cancelRun(id);await runs.load()}
export async function retry(id:string){await retryRun(id);await runs.load()}
