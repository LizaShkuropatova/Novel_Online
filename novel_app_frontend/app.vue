<template>
 <NuxtLoadingIndicator />
 <ViewState
  v-slot="path"
  src="route://path"
 >
  <ViewState
   v-slot="page"
   :src="`app-config://usebootstrap/pages`"
   :path="path.data"
  >
   <div v-if="page.data">
    <Head>
     <PageMeta
      :title="page.data.title"
      :description="page.data.description"
      :route-meta="page.data"
     >
      <LdArticle :headline="page.data.title" />
     </PageMeta>
    </Head>
    <NuxtLayout :name="page.data.layout || 'default'">
     <NuxtPage />
    </NuxtLayout>
   </div>
   <NuxtLayout
    v-else
    :name="'default'"
   >
    <NuxtPage />
   </NuxtLayout>
  </ViewState>
 </ViewState>
</template>
