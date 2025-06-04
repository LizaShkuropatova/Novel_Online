<template>
</template>

<script lang="ts" setup>
import { useAuthStore } from '@/store/auth';

const auth = useAuthStore();

onMounted(() => {
 auth.logout();
 navigateTo('/');
});
</script>
