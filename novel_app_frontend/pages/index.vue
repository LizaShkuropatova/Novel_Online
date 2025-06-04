<template>
 <Container margin="y-5">
  <NovelsPublicList />
 </Container>
</template>

<script lang="ts" setup>
import { useAuthStore } from '@/store/auth';

const auth = useAuthStore();
</script>
