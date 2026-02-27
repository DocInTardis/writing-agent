<script setup lang="ts">
import { ref } from 'vue'
import { ElButton, ElInput, ElMessage } from 'element-plus'

const instruction = ref('')
const generating = ref(false)

async function handleGenerate() {
  if (!instruction.value.trim()) {
    ElMessage.warning('请输入生成要求')
    return
  }
  
  generating.value = true
  try {
    const resp = await fetch('/api/doc/test/generate/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction: instruction.value, text: '' })
    })
    
    if (!resp.ok) throw new Error('生成失败')
    
    // 处理SSE流
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      
      const chunk = decoder.decode(value)
      console.log('SSE chunk:', chunk)
    }
    
    ElMessage.success('生成完成')
  } catch (err) {
    ElMessage.error(`生成失败: ${err}`)
  } finally {
    generating.value = false
  }
}
</script>

<template>
  <div class="workbench">
    <h1>Writing Agent - Vue POC</h1>
    <el-input 
      v-model="instruction" 
      type="textarea"
      placeholder="输入生成要求..."
      :rows="4"
    />
    <el-button 
      type="primary" 
      @click="handleGenerate"
      :loading="generating"
      style="margin-top: 16px"
    >
      开始生成
    </el-button>
  </div>
</template>

<style scoped>
.workbench {
  max-width: 800px;
  margin: 40px auto;
  padding: 20px;
}
</style>
