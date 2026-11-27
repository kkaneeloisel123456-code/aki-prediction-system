<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { AssessmentGuide } from '../api/types'
import PageHeader from '../components/PageHeader.vue'
import SectionPanel from '../components/SectionPanel.vue'

const data = ref<AssessmentGuide | null>(null)
const loading = ref(true)
const error = ref('')
const percent = (value: number) => `${Math.round(value * 100)}%`
async function load() {
  loading.value = true
  error.value = ''
  data.value = null
  try { data.value = await api.assessmentGuide() }
  catch (e: any) { error.value = e?.message || '评估说明加载失败' }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <div class="pilot-page">
    <div class="pilot-page-inner">
      <PageHeader kicker="使用帮助" title="评估说明" description="开始评估前，确认适用范围、指标时点与缺失处理；结果由医生复核后发布。">
        <template #actions><button class="pilot-btn" type="button" :disabled="loading" @click="load">刷新说明</button></template>
      </PageHeader>
      <div v-if="error" class="pilot-error" role="alert">{{ error }}。当前版本与阈值未确认，请重试。</div>
      <div v-if="loading" class="pilot-panel pilot-loading">正在读取当前模型说明…</div>
      <div v-else class="pilot-stack guide-content">
        <SectionPanel title="适用范围与边界" subtitle="围手术期 AKI 风险辅助评估">
          <p>本项目基于单中心心脏手术相关临床数据开展研究。录入前应核对患者场景与建模人群是否一致，其他人群的适用性需要另行验证。</p>
          <p>结果是模型风险估计。临床诊断、处理方案和随访建议由医生结合原始病历、检查结果及患者实际情况判断。</p>
        </SectionPanel>
        <SectionPanel title="输入要求与数据时点" subtitle="核对患者、就诊及采样阶段">
          <p>先核对姓名、病历号和本次就诊；指标按术前、术中、入 ICU、术后分组，单位与合理范围以每个输入项旁的标注为准。</p>
          <p>模型使用多个阶段的指标，不能将包含术后数据的结果解读为纯术前预测。系统未逐项记录采样时间，评估时请结合原始记录核对时点；复制上次就诊后须逐项确认。</p>
          <p v-if="data">当前模型包含 <strong>{{ data.n_features }}</strong> 项指标。</p>
        </SectionPanel>
        <SectionPanel title="缺失项与填充值" subtitle="填充值不属于患者实测结果">
          <p>缺失指标按训练数据中位数填充。接诊页中的“填充值”和报告中的“非实测”标识用于追踪这些输入；填充值不会变成患者的实测记录。</p>
          <p>超范围或格式错误应先核对修正。缺失较多时需审慎解释结果；发布前须确认缺失项。人工记录单独标识，不显示模型概率。</p>
        </SectionPanel>
        <SectionPanel title="风险结果与医生复核" subtitle="模型结果、医生意见与正式报告分开记录">
          <template v-if="data">
            <div class="guide-bands">
              <div><span>低风险</span><strong>&lt; {{ percent(data.risk_low) }}</strong></div>
              <div><span>中风险</span><strong>{{ percent(data.risk_low) }} ≤ 概率 &lt; {{ percent(data.risk_high) }}</strong></div>
              <div><span>高风险</span><strong>≥ {{ percent(data.risk_high) }}</strong></div>
            </div>
            <p>以上为系统风险分层阈值，不是诊断标准。当前{{ data.calibrated ? '已加载概率校准器' : '未加载概率校准器' }}。</p>
          </template>
          <p>评估后记录采纳、调整或暂不发布的依据。已复核记录仍须完成发布核对；“暂不发布”保留在待观察队列。服务在线表示系统可用，不能替代患者输入核对与医生复核。</p>
        </SectionPanel>
        <SectionPanel v-if="data" title="当前版本与验证摘要" subtitle="按需查看技术依据">
          <p>当前模型版本：<strong class="pilot-mono guide-version">{{ data.model_version }}</strong>。历史报告保留发布时使用的版本。</p>
          <details>
            <summary>展开内部验证摘要与局限</summary>
            <p v-if="data.validation">项目所附投票集成模型的 50 次嵌套交叉验证 AUC 均值 {{ data.validation.auc_mean.toFixed(3) }}，标准差 {{ data.validation.auc_std.toFixed(3) }}。</p>
            <p v-else>当前未提供可读取的内部验证摘要。</p>
            <p>研究数据为单中心 420 例。上述指标来自项目随附研究产物，不代表当前部署已通过外部验证，也不等同于某位患者的准确率。跨机构、跨人群及前瞻性使用仍需验证。</p>
          </details>
        </SectionPanel>
        <RouterLink to="/" class="pilot-link">← 返回工作台</RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.guide-content { max-width: 960px; margin-inline: auto; }
.guide-content p { margin: 0 0 12px; color: var(--pilot-ink-soft); line-height: 1.85; }
.guide-content p:last-child { margin-bottom: 0; }
.guide-bands { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.guide-bands div { flex: 1 1 160px; display: grid; gap: 8px; padding: 16px; border: 1px solid var(--pilot-line); border-radius: var(--pilot-radius-control); }
.guide-bands span { color: var(--pilot-muted); font-size: 12px; }
.guide-version { overflow-wrap: anywhere; }
details { padding: 16px; border: 1px solid var(--pilot-line); border-radius: var(--pilot-radius-control); }
summary { cursor: pointer; color: var(--pilot-accent); line-height: 1.8; }
details[open] summary { margin-bottom: 12px; }
</style>
