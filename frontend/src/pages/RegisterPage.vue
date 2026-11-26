<script setup lang="ts">
import { reactive, ref } from 'vue'
import { api } from '../api/client'
import ThemeSwitch from '../components/ThemeSwitch.vue'
const form = reactive({ username: '', display_name: '', institution: '', department: '', password: '' })
const confirm = ref('')
const busy = ref(false)
const error = ref('')
const message = ref('')
async function submit() {
  error.value = ''
  if (form.password !== confirm.value) { error.value = '两次输入的密码不一致'; return }
  busy.value = true
  try {
    const result = await api.registerDoctor(form)
    message.value = result.message
    form.password = ''; confirm.value = ''
  } catch (e: any) { error.value = e.message || '申请失败，请稍后再试' }
  finally { busy.value = false }
}
</script>

<template>
  <main class="registration-page">
    <aside class="registration-story">
      <RouterLink to="/login" class="pilot-link">AKI · 临床决策支持系统</RouterLink>
      <div><span class="pilot-kicker">FOR CLINICIANS</span><h1>让每一次评估，<br>都有可靠的依据。</h1><p>加入临床工作台，开展围术期风险评估、医生复核与报告管理。</p></div>
      <ol><li>填写医生资料</li><li>管理员核实身份</li><li>审核通过后登录</li></ol>
    </aside>
    <section class="registration-content">
      <div class="registration-tools"><RouterLink to="/login" class="pilot-link">← 返回登录</RouterLink><ThemeSwitch /></div>
      <div class="registration-card">
        <span class="pilot-kicker">DOCTOR REGISTRATION</span><h2>申请医生账号</h2>
        <p class="pilot-muted">仅面向医务人员。管理员核实后开通，不会立即获得患者数据访问权限。</p>
        <div v-if="message" class="registration-success" role="status"><h3>申请已受理</h3><p>{{ message }}</p><RouterLink to="/login" class="pilot-btn pilot-btn-primary">返回登录</RouterLink></div>
        <form v-else @submit.prevent="submit" class="registration-form">
          <label>姓名<input v-model.trim="form.display_name" class="pilot-input" required minlength="2" maxlength="60" autocomplete="name" placeholder="请输入真实姓名"></label>
          <label>登录账号<input v-model.trim="form.username" class="pilot-input" required minlength="3" maxlength="40" pattern="[a-zA-Z0-9_.\-]+" autocomplete="username" placeholder="3–40 位字母、数字、点、下划线或短横线"></label>
          <div class="registration-fields"><label>所在医院 / 机构<input v-model.trim="form.institution" class="pilot-input" required minlength="2" maxlength="120" autocomplete="organization"></label><label>科室<input v-model.trim="form.department" class="pilot-input" required minlength="2" maxlength="80"></label></div>
          <label>密码<input v-model="form.password" class="pilot-input" type="password" required minlength="12" maxlength="128" autocomplete="new-password" placeholder="至少 12 个字符"></label>
          <label>确认密码<input v-model="confirm" class="pilot-input" type="password" required minlength="12" maxlength="128" autocomplete="new-password" placeholder="请再次输入密码"></label>
          <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>
          <button class="pilot-btn pilot-btn-primary" :disabled="busy" type="submit">{{ busy ? '正在提交…' : '提交注册申请' }}</button>
          <p class="pilot-small">审核结果请联系本系统管理员查询。资料仅用于核实医务人员身份。</p>
        </form>
      </div>
    </section>
  </main>
</template>

<style scoped>
.registration-page{min-height:100dvh;display:grid;grid-template-columns: minmax(300px,.85fr) minmax(440px,1.15fr);background:var(--pilot-bg);color:var(--pilot-ink)}
.registration-story{padding:clamp(32px,5vw,80px);background:var(--pilot-accent-soft);display:flex;flex-direction:column;justify-content:space-between;gap:48px;border-right:1px solid var(--pilot-line)}
.registration-story h1{font-size:clamp(28px,3vw,44px);line-height:1.5;font-weight:600;letter-spacing:-1px}.registration-story p{line-height:1.9;color:var(--pilot-muted);max-width:340px}.registration-story ol{padding-left:24px;display:grid;gap:20px;color:var(--pilot-accent)}
.registration-content{padding:24px 40px;display:flex;flex-direction:column}.registration-tools{display:flex;align-items:center;justify-content:space-between;gap:16px}.registration-card{width:100%;max-width:480px;margin:auto;padding:40px 0}.registration-card h2{font-size:30px;margin:12px 0}.registration-card>p{line-height:1.8;margin-bottom:28px}.registration-form{display:grid;gap:18px}.registration-form label{display:grid;gap:8px;font-size:13px}.registration-fields{display:grid;grid-template-columns:1fr 1fr;gap:16px}.registration-form button{min-height:44px}.registration-success{padding:24px;border:1px solid var(--pilot-line);border-radius:12px;background:var(--pilot-surface);line-height:1.8}
@media(max-width:800px){.registration-page{grid-template-columns:1fr}.registration-story{display:none}.registration-content{padding:20px 24px}.registration-fields{grid-template-columns:1fr}}
</style>
