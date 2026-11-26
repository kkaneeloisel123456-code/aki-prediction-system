<script setup lang="ts">
import PageHeader from '../components/PageHeader.vue'
import SectionPanel from '../components/SectionPanel.vue'
import ResearchNav from '../components/ResearchNav.vue'
</script>

<template>
  <div class="pilot-page">
    <div class="pilot-page-inner">
      <PageHeader kicker="系统管理 / 辅助工具" title="科研与维护" description="管理员可查看研究产物与数据处理说明。日常接诊、评估和报告在临床工作区完成。" />
      <ResearchNav />
      <div class="research-grid">
        <SectionPanel title="研究验证" subtitle="模型与实验结果">
          <p>查看模型比较、ROC / PR、校准、决策曲线、交叉验证、消融及集成实验。</p>
          <RouterLink to="/performance" class="pilot-btn pilot-btn-primary">查看研究验证 →</RouterLink>
        </SectionPanel>
        <SectionPanel title="数据治理" subtitle="建模数据与处理流程">
          <p>查看训练数据质量、缺失值处理、字段统计和特征筛选过程。</p>
          <RouterLink to="/governance" class="pilot-btn">查看数据治理 →</RouterLink>
        </SectionPanel>
      </div>
      <p class="pilot-small">研究图表用于理解项目验证过程；当前部署版本、输入要求与使用局限见 <RouterLink to="/assessment-guide" class="pilot-link">评估说明</RouterLink>。</p>
    </div>
  </div>
</template>

<style scoped>
.research-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; margin-bottom: 20px; }
.research-grid p { margin: 0 0 20px; line-height: 1.8; color: var(--pilot-ink-soft); }
@media (max-width: 700px) { .research-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
