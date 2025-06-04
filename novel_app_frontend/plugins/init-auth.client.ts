import { useAuthStore } from '@/store/auth';

export default defineNuxtPlugin(async () => {
 const auth = useAuthStore();
 const token = useCookie('access_token').value;

 if (token) {
  await auth.fetchProfile();
 }
});
