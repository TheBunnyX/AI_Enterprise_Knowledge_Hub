import { describe, expect, it } from 'vitest';
import { priceText } from '../components/model-icon';

describe('model price shown in the pickers', () => {
  it('text models show input and output per 1M', () => {
    expect(priceText({ category: 'LLM', provider: 'OpenRouter', input_price: 0.1, output_price: 0.5 })).toBe('$0.1 เข้า / $0.5 ออก ต่อ 1M');
    expect(priceText({ category: 'LLM', provider: 'OpenRouter', input_price: 4, output_price: 20 })).toBe('$4 เข้า / $20 ออก ต่อ 1M');
    expect(priceText({ category: 'LLM', provider: 'OpenRouter', input_price: 0.035, output_price: 0.1405 })).toBe('$0.035 เข้า / $0.14 ออก ต่อ 1M');
  });
  it('images are priced per picture and video per second', () => {
    expect(priceText({ category: 'Image', provider: 'OpenRouter', input_price: 0, output_price: 0.003 })).toBe('$0.003 / ภาพ');
    expect(priceText({ category: 'Video', provider: 'OpenRouter', input_price: 0, output_price: 0.005 })).toBe('$0.005 / วินาที');
  });
  it('a model with no price says so, and a local model is free', () => {
    expect(priceText({ category: 'Live', provider: 'Google AI', input_price: 0, output_price: 0 })).toBe('ไม่ระบุราคา');
    expect(priceText({ category: 'Image', provider: 'OpenRouter', input_price: 0, output_price: 0 })).toBe('ไม่ระบุราคา');
    expect(priceText({ category: 'LLM', provider: 'Local LLM', input_price: 0, output_price: 0 })).toBe('ฟรี (รันในเครื่อง)');
  });
});

import { modelTitle, sourceTag } from '../components/model-icon';

describe('which route a Google model takes', () => {
  it('tells Google AI Studio from OpenRouter, and leaves other models alone', () => {
    expect(sourceTag({ provider: 'Google AI', api_id: 'gemini-3.5-flash-lite' })).toBe('Google AI Studio');
    expect(sourceTag({ provider: 'OpenRouter', api_id: 'google/gemini-3.5-flash-lite' })).toBe('OpenRouter');
    expect(sourceTag({ provider: 'OpenRouter', api_id: 'deepseek/deepseek-v4-pro-0813' })).toBe('');
    expect(sourceTag({ provider: 'Local LLM', api_id: 'qwen3.5-2b' })).toBe('');
  });
  it('puts the route after the name in plain lists', () => {
    expect(modelTitle({ name: 'Gemini 3.5 Flash Lite', provider: 'Google AI', api_id: 'gemini-3.5-flash-lite' })).toBe('Gemini 3.5 Flash Lite · Google AI Studio');
    expect(modelTitle({ display_name: 'Gemini 3.5 Flash Lite', provider: 'OpenRouter', api_id: 'google/gemini-3.5-flash-lite' })).toBe('Gemini 3.5 Flash Lite · OpenRouter');
    expect(modelTitle({ name: 'GLM 5.3', provider: 'OpenRouter', api_id: 'z-ai/glm-5.3' })).toBe('GLM 5.3');
  });
});

import { money4 } from '../components/api';

describe('cost with four decimals', () => {
  it('shows $0.0000 and keeps tiny costs visible', () => {
    expect(money4(0)).toBe('$0.0000');
    expect(money4(undefined)).toBe('$0.0000');
    expect(money4(0.0000144)).toBe('$0.0000');
    expect(money4(0.0184)).toBe('$0.0184');
    expect(money4(0.00995)).toBe('$0.0100');
    expect(money4(1234.5)).toBe('$1,234.5000');
  });
});
