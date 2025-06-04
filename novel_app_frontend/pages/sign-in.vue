<template>
 <div class="min-vh-100 d-flex flex-column justify-content-center align-items-center">
  <b-card
   class="w-100 shadow-sm border-0 px-3 py-4 card-bg"
   style="max-width: 380px"
  >
   <div class="text-center mb-3">
    <b-icon
     icon="person-circle"
     font-scale="2.5"
     class="text-primary"
    />
    <h5 class="mt-2">
     Welcome
    </h5>
    <p class="text-muted mb-0">
     Log in to your account
    </p>
   </div>

   <b-form @submit.prevent="handleLogin">
    <b-form-group
     label="Email"
     label-for="email"
     class="d-block my-2"
    >
     <b-form-input
      id="email"
      v-model="email"
      type="email"
      placeholder="name@example.com"
      required
      size="lg"
     />
    </b-form-group>

    <b-form-group
     label="Password"
     label-for="password"
     class="d-block my-2"
    >
     <b-form-input
      id="password"
      v-model="password"
      type="password"
      placeholder="Enter your password"
      required
      size="lg"
     />
    </b-form-group>

    <div class="d-flex justify-content-center">
     <b-button
      type="submit"
      size="lg"
      block
      class="btn-indigo mt-2"
     >
      Log in
     </b-button>
    </div>
   </b-form>

   <p
    class="text-center text-muted mt-3 mb-0"
    style="font-size: 0.9rem;"
   >
    No account?
    <NuxtLink
     to="/sign-up"
     class="text-primary text-decoration-none"
    >
     Sign in
    </NuxtLink>
   </p>
  </b-card>
 </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useAuthStore } from '@/store/auth';

const email = ref('user123123@example.com');
const password = ref('string123123');

const auth = useAuthStore();

async function handleLogin() {
 try {
  await auth.login(email.value, password.value);
  navigateTo('/');
 }
 catch (err) {
  console.error('Invalid login or password', err);
 }
}
</script>

<style scoped>
.bg-site {
  background-color: #f2f4f8;
}

.card-bg {
  background-color: #ffffff;
  border-radius: 1rem;
}

.btn-indigo {
  background-color: #4f46e5;
  border-color: #4f46e5;
  color: white;
}

.btn-indigo:hover {
  background-color: #4338ca;
  border-color: #4338ca;
}
</style>
