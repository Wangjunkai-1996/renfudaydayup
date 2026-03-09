import { mount } from '@vue/test-utils';

import AppCard from '@/shared/ui/AppCard.vue';

describe('AppCard', () => {
  it('renders title and slot content', () => {
    const wrapper = mount(AppCard, {
      props: { title: 'Demo Card', subtitle: 'Testing subtitle' },
      slots: { default: '<div class="demo-content">Hello</div>' },
    });

    expect(wrapper.text()).toContain('Demo Card');
    expect(wrapper.text()).toContain('Testing subtitle');
    expect(wrapper.find('.demo-content').exists()).toBe(true);
  });
});
