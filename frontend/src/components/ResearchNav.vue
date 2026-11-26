<template>
  <nav class="research-nav" aria-label="科研与维护导航">
    <RouterLink to="/admin" class="pilot-link">← 系统管理</RouterLink>
    <RouterLink to="/research" class="pilot-btn" exact-active-class="pilot-btn-primary">科研与维护</RouterLink>
    <RouterLink to="/performance" class="pilot-btn" active-class="pilot-btn-primary">研究验证</RouterLink>
    <RouterLink to="/governance" class="pilot-btn" active-class="pilot-btn-primary">数据治理</RouterLink>
  </nav>
</template>

<style scoped>
.research-nav { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
</style>
