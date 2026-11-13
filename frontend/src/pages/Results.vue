<script setup lang="ts">import {ref,computed,onMounted,onUnmounted,watch} from 'vue';import {route} from '../router';import {runs,cancel,retry} from '../stores/runs';import {reviews} from '../stores/reviews';import {canWrite} from '../stores/auth';import {useTask} from '../hooks/useTask';import {fixed,scientific} from '../utils/format';import PageHeading from '../components/common/PageHeading.vue';import StatusPill from '../components/common/StatusPill.vue';import Notice from '../components/common/Notice.vue';import EmptyState from '../components/common/EmptyState.vue';import WarningNotes from '../components/WarningNotes.vue';import KrigingMetrics from '../components/KrigingMetrics.vue';import SpatialMap from '../components/SpatialMap.vue';import VariogramPlot from '../components/VariogramPlot.vue';import PredictionTable from '../components/PredictionTable.vue';
const selected=ref(route.value.query.get('run')||'demo-run'),mode=ref<'value'|'sd'>('value'),query=ref(''),action=ref('核对局部米制口径、拟合边界和稀疏区；参数/预测锁定。空间随机场方差不当作真实误差，不补造LOO验证。'),notice=ref('');
watch(()=>route.value.query.get('run'),v=>{selected.value=v||'demo-run';query.value='';notice.value=''});
const {error,busy,act}=useTask();
let timer:ReturnType<typeof setInterval>;
onMounted(()=>{runs.load();timer=setInterval(runs.load,2000)});onUnmounted(()=>clearInterval(timer));
const run=computed(()=>runs.items.value.find(r=>r.id===selected.value));
const result=computed(()=>run.value?.result);
const ACTIVE=['queued','running','retrying'];
const isActive=computed(()=>run.value&&ACTIVE.includes(run.value.status));
const prediction=computed(()=>result.value?.kriging.predictions.find((p:any)=>p.query_id===(query.value||result.value.kriging.predictions[0]?.query_id)));
const historyLabels:Record<string,string>={failed:'计算失败',interrupted:'进程中断',cancelled:'用户取消'};
function doCancel(){act(async()=>{await cancel(selected.value);notice.value='任务已取消；已在计算的迟到结果不会写入，可随时重试。'})}
function doRetry(){act(async()=>{await retry(selected.value);notice.value='已按原输入重新排队，历次失败原因保留在下方留档。'})}
function submit(){act(async()=>{await reviews.create({run_id:selected.value,action:action.value});notice.value='空间推断复核已提交，等待管理员批准。'})}
</script>
<template><PageHeading index="04 / 运行底稿" title="地图上给出推断，也留下模型方差。" note="原始坐标、拟合参数、分箱、权重与预测均留存Double精度。排队与计算中的任务可取消，失败或中断可按原输入重试，迟到结果不覆盖新尝试。"/>
<div class="result-toolbar"><label>运行记录<select v-model="selected"><option v-for="r in runs.items.value" :key="r.id" :value="r.id">{{r.id==='demo-run'?'北地块基线':r.id.slice(0,8)}} · {{r.status}}<template v-if="r.attempt>1">（第{{r.attempt}}次尝试）</template></option></select></label><StatusPill v-if="run" :status="run.status"/></div>
<Notice :message="error||runs.error.value"/>
<Notice v-if="notice" :message="notice"/>
<div v-if="run&&canWrite()" class="run-actions">
 <button v-if="isActive" class="secondary" :disabled="busy" @click="doCancel">取消任务</button>
 <button v-if="['failed','cancelled'].includes(run.status)||(run.status==='running'&&run.stale)" :disabled="busy" @click="doRetry">按原输入重试</button>
 <small v-if="run.status==='running'&&run.stale">worker心跳已超时，任务疑似中断，可恢复重试。</small>
 <small v-else-if="run.status==='retrying'">第{{run.attempt}}次尝试排队中，沿用原采样与口径输入。</small>
</div>
<Notice v-if="run?.status==='failed'" :message="run.error||'计算失败，可按原输入重试；历次失败原因见下方留档。'"/>
<Notice v-if="run?.status==='cancelled'" :message="'任务已取消，未产生任何结果；可按原输入重新计算。'"/>
<div v-if="run?.attempts_history?.length" class="attempt-history"><p class="eyebrow">ATTEMPT LOG · 历次非成功尝试留档</p><div v-for="(h,i) in run.attempts_history" :key="i" class="attempt-row"><StatusPill :status="h.status==='interrupted'?'failed':h.status"/><span>第{{h.attempt}}次 · {{historyLabels[h.status]||h.status}} · {{h.at.replace('T',' ').replace('Z','')}}</span><p v-if="h.reason">{{h.reason}}</p></div></div>
<EmptyState v-if="run&&isActive" :text="run.status==='retrying'?'重试任务已排队，后台worker正在重新计算，结果每两秒刷新。':'后台worker正在计算变异函数与增广克里金系统，结果每两秒刷新。'"/>
<EmptyState v-if="run&&run.status==='cancelled'" text="该运行已取消，没有可展示的推断结果。点击上方按钮可按原输入重新计算。"/>
<template v-if="run?.status==='completed'&&result"><WarningNotes :rows="result.warnings"/><KrigingMetrics :result="result"/><div class="field-layout"><section><div class="section-heading"><h2>待估点与空间场</h2><label>地图着色<select v-model="mode"><option value="value">预测含水率</option><option value="sd">空间标准差</option></select></label></div><SpatialMap :points="result.points" :predictions="result.kriging.predictions" :mode="mode" :selected="prediction?.query_id" @select="query=$event"/><PredictionTable :rows="result.kriging.predictions" @select="query=$event"/></section><aside class="field-note"><p class="eyebrow">LOCKED MODEL & WEIGHTS</p><VariogramPlot :result="result"/><template v-if="prediction"><h2>{{prediction.query_id}} · 预测权重</h2><p>预测{{fixed(prediction.prediction)}}%，空间方差{{fixed(prediction.variance,6)}} pp²。权重和{{fixed(prediction.weight_sum,9)}}，mu={{fixed(prediction.mu,6)}}。</p><div class="weight-list"><div v-for="w in prediction.weights" :key="w.point_id"><span>{{w.point_id}}</span><strong>{{fixed(w.weight,7)}}</strong></div></div><p v-if="prediction.variance_clipped">原始微负方差{{scientific(prediction.raw_variance)}}已按阈值截0，原值保留。</p></template><p>{{result.kriging.model_variance_note}}</p><p>条件数{{scientific(result.kriging.condition_number)}}；微负阈值{{scientific(result.kriging.negative_variance_cutoff)}} pp²。</p><p class="hash-note">输入SHA256 {{result.input_sha256}}</p></aside></div><form v-if="canWrite()" class="review-form" @submit.prevent="submit"><label>地块复核说明<textarea v-model="action" rows="4" required minlength="8"></textarea></label><button :disabled="busy">提交空间推断复核</button><p class="success" v-if="notice">{{notice}}</p></form></template></template>
