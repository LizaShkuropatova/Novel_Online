<template>
 <Anchor
  class="card-link"
  :to="novelUrl"
 >
  <Card
   class="border-0"
   text-alignment="center"
  >
   <CardImgTop
    class="card-img-fixed"
    :src="novel.cover_image_url"
   />
   <CardBody class="p-2">
    <CardTitle :small="true">
     {{ novel.title }}
    </CardTitle>
   </CardBody>
  </Card>
 </Anchor>
</template>

<script setup>
defineProps({
 novel: Object,
 novelUrl: String,
});
</script>

<style lang="scss" scoped>
.card-link {
 text-decoration: none;
  display: flex;
  height: 100%;
}
.card-img-fixed {
  height: 150px;
  object-fit: cover;
  width: 100%;
}
</style>
