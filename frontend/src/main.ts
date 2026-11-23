import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './index.css'
import './styles/tokens.css'

const app = createApp(App).use(router)
void router.isReady().then(() => app.mount('#app'))
