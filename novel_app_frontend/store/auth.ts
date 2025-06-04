import { defineStore } from 'pinia';

/** Интерфейс под данные, которые возвращает /users/me */
export interface UserProfile {
 user_id: string;
 email: string;
 username: string;
 birthday: string | null;
 avatar: string | null;
 created_at: string;
 last_login: string;
 friends: string[];
 created_novels: string[];
 playing_novels: string[];
 planned_novels: string[];
 completed_novels: string[];
 favorite_novels: string[];
 abandoned_novels: string[];
}

export const useAuthStore = defineStore('auth', {
 state: () => ({
  accessToken: useCookie<string | null>('access_token').value,
  tokenType: useCookie<string | null>('token_type').value,
  email: useCookie<string | null>('user_email').value,
  user: null as UserProfile | null,
 }),

 getters: {
  isAuthenticated: state => !!state.accessToken,
  authHeader: state =>
   state.tokenType && state.accessToken
    ? `${state.tokenType} ${state.accessToken}`
    : '',
 },

 actions: {
  async login(email: string, password: string) {
   try {
    const { data, error } = await useFetch('http://127.0.0.1:8000/auth/login', {
     method: 'POST',
     body: { email, password },
    });

    if (error.value || !data.value?.access_token) {
     throw new Error('Authorization error');
    }

    const access_token = data.value.access_token;
    const token_type = data.value.token_type;

    // сохраняем в сторе
    this.accessToken = access_token;
    this.tokenType = token_type;
    this.email = email;

    // и в куки
    useCookie('access_token').value = access_token;
    useCookie('token_type').value = token_type;
    useCookie('user_email').value = email;

    // сразу подтягиваем профиль
    await this.fetchProfile();
   }
   catch (err) {
    console.error('[auth/login] Error:', err);
    throw err;
   }
  },

  logout() {
   this.accessToken = null;
   this.tokenType = null;
   this.email = null;
   this.user = null;

   useCookie('access_token').value = null;
   useCookie('token_type').value = null;
   useCookie('user_email').value = null;
  },

  async fetchProfile() {
   if (!this.accessToken) {
    this.user = null;
    return;
   }

   const { data, error } = await useFetch<UserProfile>(
    'http://127.0.0.1:8000/auth/me',
    {
     headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${this.accessToken}`,
     },
    },
   );

   if (error.value) {
    console.error('[auth/fetchProfile] Profile loading error:', error.value);
    this.logout();

    // Redirect to home
    navigateTo('/');
    return;
   }

   this.user = data.value!;
  },
 },
});
